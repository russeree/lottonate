import zmq
import threading
import binascii
import time
import os
import hashlib
from dotenv import load_dotenv
from queue import Queue
from flask import Flask, send_from_directory, jsonify
from coordinate.coordinate import CoordinateWallet

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='public', static_url_path='')

class BlockHashMonitor:
    def __init__(self):
        zmq_host = os.getenv('BITCOIN_ZMQ_HOST')
        zmq_port = os.getenv('BITCOIN_ZMQ_PORT')
        self.zmq_url = f"tcp://{zmq_host}:{zmq_port}"
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.running = False
        self.hash_queue = Queue()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()
        self.socket.close()
        self.context.term()

    def run(self):
        self.socket.connect(self.zmq_url)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")

        while self.running:
            try:
                topic, body, seq = self.socket.recv_multipart()
                block_hash = binascii.hexlify(body).decode('utf-8')
                print(f"New block hash received: {block_hash}")
                self.hash_queue.put(block_hash)
            except zmq.ZMQError as e:
                print(f"ZMQ Error: {e}")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")

    def get_next_hash(self):
        return self.hash_queue.get()

# Global variables
monitor = BlockHashMonitor()
coordinate_wallet = CoordinateWallet()
latest_hash = "No blocks received yet"
last_winner = None

@app.route('/')
def home():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/address')
def get_address():
    global coordinate_wallet
    address = coordinate_wallet.get_new_address()
    return jsonify({
        'address': address
    })

@app.route('/utxos')
def get_utxos():
    global coordinate_wallet
    entries = coordinate_wallet.get_unspent_txids_and_values()
    return jsonify(entries)

@app.route('/blockhash')
def get_blockhash():
    global latest_hash
    return jsonify({
        'latestHash': latest_hash
    })

@app.route('/last_winner')
def get_last_winner():
    global last_winner
    return jsonify(last_winner if last_winner else {"message": "No winner yet"})

def process_block(block_hash):
    global last_winner, coordinate_wallet
    print(f"New block found! Processing winner for block: {block_hash}")
    sha256 = hashlib.sha256(block_hash.encode()).hexdigest()
    print(f"SHA256 of the block hash: {sha256}")

    # Get all unspent transactions
    unspent_txs = coordinate_wallet.get_unspent_txids_and_values()

    if not unspent_txs:
        print("No unspent transactions found.")
        return

    # Find the TXID with the smallest difference from the block hash SHA256
    smallest_diff = float('inf')
    winning_txid = None

    for tx in unspent_txs:
        diff = abs(int(sha256, 16) - int(tx['txid'], 16))
        if diff < smallest_diff:
            smallest_diff = diff
            winning_txid = tx['txid']

    if winning_txid:
        print(f"Winning TXID: {winning_txid}")

        # Get input addresses for the winning TXID
        input_addresses = coordinate_wallet.get_input_addresses(winning_txid)

        winner_address = None
        if input_addresses:
            for address in input_addresses:
                if address:  # Check if the address is valid (not None or empty string)
                    winner_address = address
                    coordinate_wallet.send_all_to_address(address)
                    break

        if winner_address:
            print(f"Winner address: {winner_address}")
            last_winner = {
                "winner_address": winner_address,
                "prize_amount": next((tx['value'] for tx in unspent_txs if tx['txid']), 0)
            }
        else:
            print("No valid winner address found.")
            last_winner = {
                "winner_address": None,
                "prize_amount": 0
            }
    else:
        print("No winning transaction found.")
        last_winner = None

    print("Winner processing completed!")

def process_hashes(monitor):
    global latest_hash
    while True:
        block_hash = monitor.get_next_hash()
        latest_hash = block_hash
        process_block(block_hash)

def run_flask():
    app.run(host='0.0.0.0', port=30000, debug=True, use_reloader=False)

if __name__ == "__main__":
    try:
        # Start the block hash monitor
        monitor.start()
        print("Block hash monitor started.")

        # Start hash processing in a separate thread
        process_thread = threading.Thread(target=process_hashes, args=(monitor,))
        process_thread.daemon = True
        process_thread.start()

        # Start the Flask server in a separate thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping block hash monitor...")
        monitor.stop()
        print("Block hash monitor stopped.")
