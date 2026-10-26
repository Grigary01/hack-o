"""Скачать закреплённый официальный CLI без GUI. Java 17 устанавливается отдельно.

Сборка хранится только в runtime, не входит в git и исходный архив проекта.
Контрольная сумма фиксирует использованную нами версию, не обновляем latest молча.
"""
import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile
import httpx

URL = 'https://github.com/Universite-Gustave-Eiffel/NoiseModelling/releases/download/v5.0.1/NoiseModelling_without_gui-5.0.1.zip'
SHA256 = '876ed1c69525ffa999779a0c4d3d00898d693f6e058fc951d11b4068eddb9f86'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('runtime/tools/noisemodelling'))
    parser.add_argument('--archive', type=Path, help='Уже скачанный zip: установка без интернета')
    args = parser.parse_args()
    archive = args.archive or args.directory.parent/'noisemodelling-5.0.1.zip'
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        temp = archive.with_suffix('.download')
        with httpx.stream('GET', URL, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with temp.open('wb') as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
        temp.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('SHA256 архива не совпадает; распаковка отменена')
    target = args.directory.resolve()
    with ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (target/name).resolve().is_relative_to(target):
                raise ValueError('Недопустимый путь в архиве')
        bundle.extractall(target)
    print(f'NOISEMODELLING_HOME={target / "NoiseModelling_without_gui-5.0.1"}')
    print('Для запуска установите Java 17 и задайте NOISE_JAVA_HOME (или JAVA_HOME).')


if __name__ == '__main__':
    main()
