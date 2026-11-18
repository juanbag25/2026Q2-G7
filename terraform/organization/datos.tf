# Sección 08: RDS PostgreSQL 16, db.t3.micro, cifrada, en las subredes de datos. Multi-AZ: una
# instancia activa y un standby sincrónico en la otra zona, con failover automático. Solo la
# alcanzan api y procesador.

resource "aws_db_subnet_group" "ateneo" {
  name       = "ateneo-datos"
  subnet_ids = local.sub["datos"]
  tags       = { Name = "ateneo-datos" }
}

# Sin / @ " ni espacios (RDS no los acepta); el resto se codifica al armar la URL.
resource "random_password" "db" {
  length           = 24
  special          = true
  override_special = "!#%*-_=+"
}

resource "aws_db_instance" "ateneo" {
  identifier     = "ateneo-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 0
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "ateneo"
  username = "ateneo"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.ateneo.name
  vpc_security_group_ids = [local.sg["db"]]
  publicly_accessible    = false
  multi_az               = true

  backup_retention_period = 7
  deletion_protection     = false
  skip_final_snapshot     = true
  apply_immediately       = true

  # Habilitado pero sin usar: la aplicación entra con la contraseña que lee de Secrets Manager.
  # Está para que un humano pueda conectarse con un token de IAM en vez de pedir la contraseña.
  iam_database_authentication_enabled = true

  tags = { Name = "ateneo-db" }
}

# La URL completa, en Secrets Manager: ECS la inyecta como DATABASE_URL a api y procesador al
# arrancar la tarea, sin que el código la pida. Ninguna otra tarea la recibe.
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "ateneo/database-url"
  description             = "postgresql:// de RDS para api y procesador"
  recovery_window_in_days = 0 # terraform destroy la borra en el acto, y el próximo apply la recrea
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://ateneo:${urlencode(random_password.db.result)}@${aws_db_instance.ateneo.address}:5432/ateneo"
}
