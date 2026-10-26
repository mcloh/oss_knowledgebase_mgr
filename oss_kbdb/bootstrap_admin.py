"""Cria o primeiro administrador do control plane; não expõe senha em argumentos."""
from __future__ import annotations
import getpass, os
from argon2 import PasswordHasher
from oss_kbdb.adapters.postgres import PostgresRepository
from oss_kbdb.config import Settings

def main() -> int:
    email=input('E-mail do administrador: ').strip().lower()
    if not email or '@' not in email: raise SystemExit('e-mail inválido')
    password=getpass.getpass('Senha: ')
    confirm=getpass.getpass('Confirme a senha: ')
    if len(password)<16 or password!=confirm: raise SystemExit('senha inválida ou divergente; mínimo 16 caracteres')
    repo=PostgresRepository(Settings.from_env().database_url)
    try:
        row=repo._conn.execute('SELECT count(*) FROM users WHERE role=%s',('admin',)).fetchone()
        if row[0]: raise SystemExit('já existe administrador; use fluxo de gestão de usuários')
        repo._conn.execute('INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s)',(email,PasswordHasher().hash(password),'admin'))
        repo._conn.commit()
    finally: repo.close()
    print('Administrador criado.')
    return 0
if __name__=='__main__': raise SystemExit(main())
