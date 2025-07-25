import json
import logging
from sys import exit
from pathlib import Path
from os import getenv
from src import (
    r2,
    utils,
    release,
    downloader
)

def run_build(app_name: str, source: str) -> str:
    download_files, name = downloader.download_required(source)

    revanced_cli = utils.find_file(download_files, 'revanced-cli', '.jar')
    revanced_patches = utils.find_file(download_files, 'patches', '.rvp')

    download_methods = [
        downloader.download_apkmirror,
        downloader.download_apkpure,
        downloader.download_uptodown
    ]

    input_apk = None
    version = None
    for method in download_methods:
        input_apk, version = method(app_name, revanced_cli, revanced_patches)
        if input_apk:
            break

    if input_apk.suffix != ".apk":
        logging.warning("Input file is not .apk, using APKEditor to merge")
        apk_editor = downloader.download_apkeditor()

        merged_apk = input_apk.with_suffix(".apk")

        utils.run_process([
            "java", "-jar", apk_editor, "m",
            "-i", str(input_apk),
            "-o", str(merged_apk)
        ], silent=True)

        input_apk.unlink(missing_ok=True)

        if not merged_apk.exists():
            logging.error("Merged APK file not found")
            exit(1)

        input_apk = merged_apk
        logging.info(f"Merged APK file generated: {input_apk}")

    exclude_patches = []
    include_patches = []

    patches_path = Path("patches") / f"{app_name}-{source}.txt"
    if patches_path.exists():
        with patches_path.open('r') as patches_file:
            for line in patches_file:
                line = line.strip()
                if line.startswith('-'):
                    exclude_patches.extend(["-d", line[1:].strip()])
                elif line.startswith('+'):
                    include_patches.extend(["-e", line[1:].strip()])

    utils.run_process([
        "zip", "--delete", str(input_apk), "lib/x86/*", "lib/x86_64/*"
    ], silent=True, check=False)

    output_apk = Path(f"{app_name}-patch-v{version}.apk")

    utils.run_process([
        "java", "-jar", str(revanced_cli),
        "patch", "--patches", str(revanced_patches),
        "--out", str(output_apk), str(input_apk),
        *exclude_patches, *include_patches
    ], stream=True)

    input_apk.unlink(missing_ok=True)

    signed_apk = Path(f"{app_name}-{name}-v{version}.apk")

    apksigner = utils.find_apksigner()
    if not apksigner:
        exit(1)

    utils.run_process([
        str(apksigner), "sign", "--verbose",
        "--ks", "keystore/public.jks",
        "--ks-pass", "pass:public",
        "--key-pass", "pass:public",
        "--ks-key-alias", "public",
        "--in", str(output_apk), "--out", str(signed_apk)
    ], stream=True)

    output_apk.unlink(missing_ok=True)
    release.create_github_release(name, revanced_patches, revanced_cli, signed_apk)
    # r2.upload(str(signed_apk), f"{app_name}/{signed_apk.name}")

if __name__ == "__main__":
    app_name = getenv("APP_NAME")
    source = getenv("SOURCE")

    if not app_name or not source:
        logging.error("APP_NAME and SOURCE environment variables must be set")
        exit(1)

    run_build(app_name, source)
