@secure()
param token string
targetScope = 'subscription'

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: '${deployment().name}rg'
  location: deployment().location
}

module funcapp 'funcapp.bicep' = {
  name: 'funcapp'
  scope: rg
}

module logicapps 'logicapps.bicep' = {
  name: 'logicapps'
  scope: rg
}
