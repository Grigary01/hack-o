"""Собирает переносимый исходный проект с данными, без среды, секретов и рабочей БД."""
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from app.core.config import ROOT


ROOT_FILES = ('.env.example', '.gitignore', 'LICENSE', 'README.md', 'main.py',
               'THIRD_PARTY_NOTICES.md', 'pyproject.toml', 'requirements.lock', 'alembic.ini',
               'Dockerfile', '.dockerignore', 'compose.yaml', 'Makefile')
PROJECT_DIRS = ('app', 'config', 'frontend', 'scripts', 'tests', 'data', 'docs', 'legacy', 'migrations', 'docker', 'web')


def project_files():
    """Явный allowlist: случайный .env или runtime никогда не попадёт в архив."""
    files = [ROOT / name for name in ROOT_FILES]
    for directory in PROJECT_DIRS:
        files.extend(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and not path.is_symlink()
                     and not {'__pycache__', 'node_modules', 'dist', '.git'}.intersection(path.parts)
                     and path.name != '.DS_Store' and path.suffix not in ('.pyc', '.pyo')
                     and not path.name.startswith('.'))
    return sorted(files)


def main():
    target = ROOT / 'artifacts'
    target.mkdir(exist_ok=True)
    archive = target / 'ostrovok-adler-mvp.zip'
    files = project_files()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=6) as output:
        for path in files:
            output.write(path, Path('ostrovok-adler-mvp') / path.relative_to(ROOT))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n')
    print(f'{archive}\n{len(files)} files; {archive.stat().st_size} bytes\nSHA256: {checksum}')


if __name__ == '__main__':
    main()
