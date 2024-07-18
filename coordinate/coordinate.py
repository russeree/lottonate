import requests
import json
import os
from dotenv import load_dotenv

class CoordinateWallet:
    def __init__(self):
        load_dotenv()
        self.rpc_user = os.getenv('COORDINATE_RPC_USER')
        self.rpc_password = os.getenv('COORDINATE_RPC_PASS')
        self.rpc_host = os.getenv('COORDINATE_RPC_HOST')
        self.rpc_port = os.getenv('COORDINATE_RPC_PORT')
        self.rpc_url = f"http://{self.rpc_host}:{self.rpc_port}"

    def _rpc_call(self, method, params=[]):
        headers = {'content-type': 'application/json'}
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": "python",
            "method": method,
            "params": params
        })
        response = requests.post(
            self.rpc_url,
            auth=(self.rpc_user, self.rpc_password),
            headers=headers,
            data=payload
        )
        if response.status_code != 200:
            raise Exception(f"RPC call failed with status code: {response.status_code}")
        return response.json()['result']

    def get_new_address(self, label="", address_type="bech32"):
        """
        Get a new Coordinate address from the wallet.
        :param label: An optional label for the address
        :param address_type: The type of address to create (legacy, p2sh-segwit, or bech32)
        :return: A new Coordinate address
        """
        try:
            result = self._rpc_call("getnewaddress", [label, address_type])
            return result
        except Exception as e:
            print(f"Error getting new address: {str(e)}")
            return None

    def get_balance(self):
        """
        Get the total balance of the wallet.
        :return: The balance in Coordinate
        """
        try:
            result = self._rpc_call("getbalance")
            return result
        except Exception as e:
            print(f"Error getting balance: {str(e)}")
            return None

    def get_unspent_txids_and_values(self, min_conf=1, max_conf=9999999):
        """
        Get the txids and values of unspent transactions.
        :param min_conf: The minimum confirmations required (default 1)
        :param max_conf: The maximum confirmations required (default 9999999)
        :return: A list of dictionaries containing txid and value of unspent transactions
        """
        try:
            unspent = self._rpc_call("listunspent", [min_conf, max_conf])
            return [{"txid": utxo["txid"], "value": utxo["amount"]} for utxo in unspent]
        except Exception as e:
            print(f"Error getting unspent transactions: {str(e)}")
            return None

    def get_input_addresses(self, txid):
        """
        Get the input addresses of a transaction given its TXID.
        Assumes 'prevout' information is always present.
        :param txid: The transaction ID
        :return: A list of input addresses or None if there's an error
        """
        try:
            # Get the full transaction details
            tx_details = self._rpc_call("getrawtransaction", [txid, 2])
            input_addresses = []
            for vin in tx_details['vin']:
                print(vin)
                # Extract the address from the prevout scriptPubKey
                address = vin['prevout']['scriptPubKey'].get('address')
                if address:
                    input_addresses.append(address)

            return input_addresses if input_addresses else None
        except Exception as e:
            print(f"Error getting input addresses for transaction {txid}: {str(e)}")
            return None

    def send_all_to_address(self, to_address):
        """
        Sends all available BTC in the wallet to the specified address.
        :param to_address: The address to send all funds to
        :return: The transaction ID if successful, None otherwise
        """
        try:
            # Get the total balance
            balance = self._rpc_call("getbalance")

            if balance <= 0:
                print("No funds available to send.")
                return None

            # Estimate the fee for the transaction
            # We'll use a conservative estimate of 1000 satoshis per byte, and assume a transaction size of 250 bytes
            estimated_fee = 0.00010000  # 250 * 1000 satoshis = 0.00000250 BTC

            # Calculate the amount to send (total balance minus the estimated fee)
            amount_to_send = balance - estimated_fee

            if amount_to_send <= 0:
                print("Balance too low to cover the transaction fee.")
                return None

            # Create the raw transaction
            inputs = self._rpc_call("listunspent")
            raw_tx = self._rpc_call("createrawtransaction", [inputs, {to_address: amount_to_send}])

            # Sign the raw transaction
            signed_tx = self._rpc_call("signrawtransactionwithwallet", [raw_tx])

            if not signed_tx.get('complete', False):
                print("Failed to sign the transaction.")
                return None

            # Send the signed transaction
            tx_id = self._rpc_call("sendrawtransaction", [signed_tx['hex']])

            print(f"Successfully sent {amount_to_send} BTC to {to_address}")
            print(f"Transaction ID: {tx_id}")

            return tx_id

        except Exception as e:
            print(f"Error sending all funds to {to_address}: {str(e)}")
            return None
