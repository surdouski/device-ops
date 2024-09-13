import time
import ssl
import sys

import click
from rich.console import Console
from rich.table import Table
import paho.mqtt.client as mqtt
from dotenv import dotenv_values

from sniffs import Sniffs

console = Console()

config = dotenv_values(".config")
_location = config.get("LOCATION")
if not _location:
    console.print("[bold red]Error: Must include a [bold orchid2].config[/bold orchid2] file with [orange3]LOCATION[/orange3][bright_white]=[/bright_white][italic magenta]location[/italic magenta].")
    sys.exit(1)

secrets = dotenv_values(".secrets")
_user = secrets.get("MQTT_SERVER_USER")
_password = secrets.get("MQTT_SERVER_PASS")
_host = secrets.get("MQTT_SERVER_IP")
_port = int(secrets.get("MQTT_SERVER_PORT") or 0)
if not (_user and _password and _host and _port):
    console.print("[bold red]Error: Must include a [bold orchid2].secrets[/bold orchid2] file with the following items:[/bold red]\n"
                  "[orange3]MQTT_SERVER_USER[/orange3][bright_white]=[/bright_white][italic magenta]some_user[/italic magenta].\n"
                  "[orange3]MQTT_SERVER_PASS[/orange3][bright_white]=[/bright_white][italic magenta]hunter2[/italic magenta].\n"
                  "[orange3]MQTT_SERVER_IP[/orange3][bright_white]=[/bright_white][italic magenta]foo.com[/italic magenta].\n"
                  "[orange3]MQTT_SERVER_PORT[/orange3][bright_white]=[/bright_white][italic magenta]1337[/italic magenta].")
    sys.exit(1)

devices_dict = {}

sniffs = Sniffs()


@sniffs.route("<location>:{" + _location + "}/devices/<device_id>/<setting>")
def device_settings(device_id, setting, message):
    if isinstance(message, bytes):
        message = message.decode()
    if device_id not in devices_dict.keys():
        devices_dict[device_id] = {}
    devices_dict[device_id][setting] = message


client = mqtt.Client(client_id="dops_client")
client.username_pw_set(_user, password=_password)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.connect(_host, _port)
sniffs.bind(client)
client.loop_start()
time.sleep(0.5)  # hopefully long enough? can't find a better way to do this atm
client.loop_stop()


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
@click.option(
    "--type",
    "-t",
    "new_value_type",
    type=click.Choice(["str", "bytes", "bytearray", "float"]),
    help="Type of the published value. (will be cast)",
)
def devices(device_id, setting_id, new_value, new_value_type):
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

    if is_command_list_devices:
        if not devices_dict.keys():
            console.print(
                f"No devices found at [{Clr.loc}]{_location}[/{Clr.loc}]."
            )
            return

        table = Table()
        table.add_column("Device", style=Clr.dev)
        for device_id in devices_dict.keys():
            table.add_row(device_id)
        console.print(table)
        return

    device = devices_dict.get(device_id)
    if not device:
        console.print(
            f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}] not found at [{Clr.loc}]{_location}[/{Clr.loc}]."
        )
        return

    if is_command_get_device_setting or is_command_set_device_setting:
        if not device.get(setting_id):
            console.print(
                f"Device: [{Clr.dev}]{device_id}[/{Clr.dev}] and setting: [{Clr.set}]{setting_id}[/{Clr.set}] not found at [{Clr.loc}]{_location}[/{Clr.loc}]."
            )
            return
        # if --set or --type is provided, the other is expected
        if (new_value or new_value_type) and not (new_value and new_value_type):
            console.print(
                f"When providing a new setting value, must specify both --set and --type options."
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
        if new_value_type == "float":
            new_value = float(new_value)
        elif new_value_type == "bytearray":
            new_value = bytearray(new_value)
        elif new_value_type == "bytes":
            new_value = bytes(new_value)
        elif new_value_type == "str":
            new_value = str(new_value)

        topic = f"{_location}/devices/{device_id}/{setting_id}"
        client.publish(topic, new_value, retain=True)


if __name__ == "__main__":
    dops()
