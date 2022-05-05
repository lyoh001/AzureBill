import calendar
import datetime
import glob
import io
import logging
import os
import tempfile

import azure.functions as func
import pandas as pd
import requests
from azure.storage.blob import BlobServiceClient


def main(mytimer: func.TimerRequest) -> None:
    # debugging start the function
    logging.info("--------------------------------------------")
    logging.info(f"*** Generating monthly Azure bill ***")

    # preparing headers and variables
    subtract_days = 15
    finance_container_name = "azure-usage-and-charges-v2-ds"
    azure_bill_table_container_name = "azurebilltable"
    azure_bill_container_name = "azurebill"
    enrollment_number = os.environ["ENROLLMENT_NUMBER"]
    ea_api_headers = {
        "Authorization": f"Bearer {os.environ['PRIMARY_EA_API_TOKEN']}",
        "Content-Type": "application/json",
    }
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed constructing api headers ***")

    # constructing marketplace charges
    marketplace_url = f"https://consumption.azure.com/v3/enrollments/{enrollment_number}/billingPeriods/{(billing_period := (month := str(datetime.date.today() - datetime.timedelta(days=subtract_days)).split('-'))[0] + month[1])}/marketplacecharges"
    try:
        marketplace_df = pd.DataFrame(
            requests.get(
                url=marketplace_url, headers=ea_api_headers, verify=True
            ).json()
        )
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    marketplace_df.rename(
        columns={col: f"{col[0].upper()}{col[1:]}" for col in marketplace_df.columns},
        inplace=True,
    )
    marketplace_df.rename(
        columns={"ExtendedCost": "Cost", "AccountOwnerId": "AccountOwnerEmail"},
        inplace=True,
    )
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed executing marketplace_df ***")

    # constructing reserved instance charges
    reserved_instance_url = f"https://consumption.azure.com/v4/enrollments/{enrollment_number}/reservationcharges?startDate={month[0]}-{month[1]}-01&endDate={month[0]}-{month[1]}-{calendar.monthrange(int(month[0]), int(month[1]))[1]}"
    try:
        reserved_instance_df = pd.DataFrame(
            requests.get(
                url=reserved_instance_url, headers=ea_api_headers, verify=True
            ).json()
        )
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    reserved_instance_df.rename(
        columns={
            col: f"{col[0].upper()}{col[1:]}" for col in reserved_instance_df.columns
        },
        inplace=True,
    )
    reserved_instance_df.rename(
        columns={
            "Region": "ResourceLocation",
            "EventDate": "Date",
            "Amount": "Cost",
            "PurchasingSubscriptionGuid": "SubscriptionGuid",
            "PurchasingSubscriptionName": "SubscriptionName",
            "Quantity": "ConsumedQuantity",
        },
        inplace=True,
    )
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed executing reserved_instance_df ***")

    # constructing usage detail charges
    usage_detail_url = f"https://consumption.azure.com/v3/enrollments/{enrollment_number}/usagedetails/submit?billingPeriod={billing_period}"
    try:
        report_url = requests.post(url=usage_detail_url, headers=ea_api_headers).json()[
            "reportUrl"
        ]
        while True:
            if (
                response := requests.get(url=report_url, headers=ea_api_headers).json()
            )["status"] == 3:
                logging.info(f"status_code: {response['status']}")
                break
            logging.info(f"status_code: {response['status']}")
        logging.info(f"blob_path: {response['blobPath']}")
        payload = requests.get(url=response["blobPath"], allow_redirects=True).text
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    usage_detail_df = pd.read_csv(io.StringIO(payload), sep=",", header=1)
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed executing usage_detail_df ***")

    # merging usage_detail_df, marketplace_df, reserved_instance_df
    combined_df = pd.concat([usage_detail_df, marketplace_df, reserved_instance_df])
    combined_df.sort_values(by=["Date"], inplace=True)
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed executing merging data frames ***")

    # exporting to csv and saving it locally
    with tempfile.TemporaryDirectory() as tempdir_path:
        path = os.path.join(
            tempdir_path,
            (file_name := f"azure_usage_and_charges_v2_ds_{billing_period}.csv"),
        )
        combined_df.to_csv(path, index=False)
        logging.info("--------------------------------------------")
        logging.info(f"*** Completed exporting to csv locally ***")

        # uploading to azure storage account
        blob_service_client = BlobServiceClient.from_connection_string(
            os.environ["FINANCE_STORAGE_ACCOUNT_CONNECTION_STRING"]
        )
        blob_client = blob_service_client.get_blob_client(
            finance_container_name, file_name
        )
        with open(path, "r") as file_reader:
            file_data = file_reader.read()
            try:
                blob_client.upload_blob(file_data)
                logging.info("--------------------------------------------")
                logging.info(f"*** Completed uploading to azure storage account ***")
            except Exception as e:
                logging.info(f"{e}")

            # debugging file_name, path, tempdir_path
            logging.info("--------------------------------------------")
            logging.info(f"*** URL: {reserved_instance_url} ***")
            logging.info(f"*** File Name: {file_name} ***")
            logging.info(f"*** Path: {path} ***")
            logging.info(f"*** Glob: {glob.glob(f'{tempdir_path}/*')} ***")
            logging.info("--------------------------------------------")

    # constructing report charges for individual subs
    report_df = usage_detail_df[
        [
            "SubscriptionName",
            "Date",
            "ServiceName",
            "Product",
            "MeterName",
            "Location",
            "Cost",
            "ConsumedQuantity",
            "ResourceRate",
            "UnitOfMeasure",
            "InstanceId",
        ]
    ]
    subscriptions = report_df["SubscriptionName"].unique()

    # reading azure bill table for adding a service fee
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            os.environ["AZBILL_STORAGE_ACCOUNT_CONNECTION_STRING"]
        )
        blob_client = blob_service_client.get_blob_client(
            azure_bill_table_container_name, "azurebilltable.csv"
        )
        azure_bill_table = {
            (col := row.split(","))[0]: float(col[1])
            for row in blob_client.download_blob()
            .content_as_text(encoding="UTF-8")
            .splitlines()[1:]
        }
        # uploading to azure storage account
        with tempfile.TemporaryDirectory() as tempdir_path:
            for sub in subscriptions:
                if sub in azure_bill_table:
                    sub_df = report_df[report_df["SubscriptionName"] == sub]
                    sub_df["Cost"] *= azure_bill_table[sub]
                    sub_df["ResourceRate"] *= azure_bill_table[sub]
                    sub_df.sort_values(by=["Date"], inplace=True)
                    path = os.path.join(
                        tempdir_path,
                        (file_name := f"{sub}_{billing_period}.csv"),
                    )
                    sub_df.to_csv(path, index=False)
                    logging.info("--------------------------------------------")
                    logging.info(
                        f"*** Completed exporting {sub}_{billing_period}.csv locally ***"
                    )
                    with open(path, "r") as file_reader:
                        file_data = file_reader.read()
                        try:
                            blob_service_client.get_blob_client(
                                azure_bill_container_name, file_name
                            ).upload_blob(file_data)
                            logging.info("--------------------------------------------")
                            logging.info(
                                f"*** Completed uploading {sub}_{billing_period}.csv to azure storage account ***"
                            )
                        except Exception as e:
                            logging.info(f"{e}")
    except Exception as e:
        logging.info(f"{e}")
    logging.info("--------------------------------------------")
    logging.info(f"*** Completed reading azure bill table ***")
