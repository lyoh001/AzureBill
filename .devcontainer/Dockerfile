FROM ubuntu:20.04

ENV TZ=Australia/Melbourne

RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update -y && apt-get install sudo -y

RUN DEBIAN_FRONTEND=noninteractive \
    && sudo apt-get update -y \
    && sudo apt-get install wget -y \
    && sudo apt-get install software-properties-common -y \
    && sudo apt-get install zsh -y \
    && sudo apt-get install tzdata -y \
    && sudo ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && wget https://packages.microsoft.com/config/debian/10/packages-microsoft-prod.deb -O packages-microsoft-prod.deb \
    && sudo dpkg -i packages-microsoft-prod.deb \
    && sudo apt-get update -y \
    && sudo apt-get dist-upgrade -y \
    && sudo apt-get install dotnet-sdk-3.1 -y \
    && sudo apt-get install git -y \
    && sudo apt-get install npm -y \
    && sudo apt-get install python3.8 -y \
    && sudo apt-get install python3-pip -y \
    && sudo apt-get install python3-venv -y \
    && sudo npm install -g npm@latest \
    && sudo npm install -g azure-functions-core-tools@3 --unsafe-perm true \
    && python3 -m pip install --upgrade pip \
    && sh -c "$(wget https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"

EXPOSE 10000