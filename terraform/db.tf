resource "azurerm_resource_group" "example" {
  name     = "example-resources"
  location = "East US"
}

resource "azurerm_postgresql_flexible_server" "example" {
  name                = "examplepgserver"
  resource_group_name = azurerm_resource_group.example.name
  location            = azurerm_resource_group.example.location
  administrator_login = "adminuser"
  administrator_password = "H@Sh1CoR3!"

  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768
  version    = "12"

  tags = {
    environment = "production"
  }
}

resource "azurerm_postgresql_flexible_server_database" "example" {
  name     = "exampledb"
  server_id = azurerm_postgresql_flexible_server.example.id
  collation = "en_US.utf8"
}

output "DB_HOSTNAME" {
  value = azurerm_postgresql_flexible_server.example.fqdn
}

output "DB_USERNAME" {
  value = azurerm_postgresql_flexible_server.example.administrator_login
}

output "DB_PASSWORD" {
  value     = azurerm_postgresql_flexible_server.example.administrator_password
  sensitive = true
}

output "DB_NAME" {
  value = azurerm_postgresql_flexible_server_database.example.name
}

output "DB_PORT" {
  value = 5432
}