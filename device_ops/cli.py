import time
import ssl
import sys
import os

import click
from rich.console import Console
from rich.table import Table
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from sniffs import Sniffs

DEFAULT_DEVICES_TOPIC = "test/devices"

console = Console()

print_settings_string = ""

def add_print_setting(setting_key: str, setting_value: str):
    global print_settings_string
    print_settings_string += f"[orange3]{setting_key}[/orange3][magenta]:[/magenta] [bright_white]{setting_value}[magenta];[/magenta] "

load_dotenv(".config")
_devices_topic = os.getenv("MQTT_DEVICES_TOPIC", DEFAULT_DEVICES_TOPIC)
add_print_setting("MQTT_DEVICES_TOPIC", _devices_topic)

secrets = load_dotenv(".secrets")
_user = os.getenv("MQTT_SERVER_USER")
if _user:
    add_print_setting("MQTT_SERVER_USER", _user)
_password = os.getenv("MQTT_SERVER_PASS")
if _user and not _password:
    console.print(f"[bold red]Error: Must set [orange3]MQTT_SERVER_PASSWORD[/orange3] if [orange3]MQTT_SERVER_USER[/orange3] is set.[/bold red]")
    sys.exit(1)
_host = os.getenv("MQTT_SERVER_HOST", "localhost")
add_print_setting("MQTT_SERVER_HOST", _host)
_port = int(os.getenv("MQTT_SERVER_PORT", 1883))
add_print_setting("MQTT_SERVER_PORT", str(_port))

console.print(print_settings_string)
devices_dict = {}
sniffs = Sniffs()

@sniffs.route(_devices_topic.rstrip("/").lstrip("/") + "/<device_id>/<setting>")
def device_settings(device_id, setting, message):
    if isinstance(message, bytes):
        message = message.decode()
    if device_id not in devices_dict.keys():
        devices_dict[device_id] = {}
    devices_dict[device_id][setting] = message


def run_client() -> mqtt.Client:
    client = mqtt.Client(client_id="dops_client")
    if _user and _password:
        client.username_pw_set(_user, password=_password)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.connect(_host, _port)
    sniffs.bind(client)
    client.loop_start()
    time.sleep(0.5)  # hopefully long enough? can't find a better way to do this atm
    client.loop_stop()  # don't need to keep client running: can still publish without looping
    return client


class Clr:
    loc = "orange1"
    dev = "chartreuse3"
    set = "cyan1"
    val = "magenta"


@click.group()
def dops():
    """Device Operations Command Line Interface"""
    pass


@dops.command()
def auth():
    """Check current authentication details."""
    for key, val in secrets.items():
        print(f"{key}: {val}")


@dops.command()
@click.argument("device_id", required=False)
@click.argument("setting_id", required=False)
@click.option("--set", "-s", "new_value", help="Value to publish/set.")
def devices(device_id, setting_id, new_value):
    """
    Shows device settings, or updates a specific device setting.

    \b
    Usage:
    dops devices
    dops devices <device_id>
    dops devices <device_id> <setting_id>
    dops devices <device_id> <setting_id> [--set]/[-s] <value> [--type]/[-t] <_type>
    """
    is_command_list_devices = not device_id
    is_command_get_device = not setting_id
    is_command_set_device_setting = not not new_value
    is_command_get_device_setting = (
        not is_command_get_device and not is_command_set_device_setting
    )

    # Call this from inside devices to delay running until options validation is done
    client = run_client()

    if is_command_list_devices:
        if not devices_dict.keys():
            console.print(
                f"No devices found at [{Clr.loc}]{_devices_topic}[/{Clr.loc}]."
            )
            return

        table = Table()
        table.add_column("Devices", style=Clr.dev)
        for device_id in devices_dict.keys():
            table.add_row(device_id)
        console.print(table)
        return

    device = devices_dict.get(device_id)
    if not device:
        console.print(
            f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}] not found at [{Clr.loc}]{_devices_topic}[/{Clr.loc}]."
        )
        return

    if is_command_get_device_setting or is_command_set_device_setting:
        if not device.get(setting_id):
            console.print(
                f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}] and setting: [{Clr.set}]{setting_id}[/{Clr.set}] not found at [{Clr.loc}]{_devices_topic}[/{Clr.loc}]."
            )
            return

    if is_command_get_device:
        table = Table(title=f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}]")
        table.add_column("Setting", style=Clr.set)
        table.add_column("Value", style=Clr.val)
        for setting, value in device.items():
            table.add_row(setting, value)
        console.print(table)

    elif is_command_get_device_setting:
        table = Table(title=f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}]")
        table.add_column("Setting", style=Clr.set)
        table.add_column("Value", style=Clr.val)

        table.add_row(setting_id, device.get(setting_id))

        console.print(table)

    elif is_command_set_device_setting:
        topic = f"{_devices_topic}/{device_id}/{setting_id}"
        client.publish(topic, new_value, retain=True)
        client.loop_start()
        time.sleep(0.5)
        client.loop_stop()

        table = Table(title=f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}]")
        table.add_column("Setting", style=Clr.set)
        table.add_column("Value", style=Clr.val)

        table.add_row(setting_id, device.get(setting_id))

        console.print(table)


if __name__ == "__main__":
    dops()
