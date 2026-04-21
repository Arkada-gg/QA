import json
import time
import requests

from web3 import Web3, Account
from eth_account.messages import encode_defunct

Account.enable_unaudited_hdwallet_features()

# ---------------- CONFIG ----------------

SIGNUP_URL = "https://app-api.arkada.gg/auth/signup"
VERIFY_URL = "https://app-api.arkada.gg/wallet/verify"
FAUCET_URL = "https://nft-api.x1eco.com/testnet/faucet"

CHAIN_ID = 10778

VERIFICATION_MESSAGE = "Welcome to Arkada!\n\nThis request will not trigger a blockchain transaction or cost any gas fees.\n\nIt's needed to authenticate your wallet address."

HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

START_FROM = 17

# ---------------- WEB3 ----------------

RPC = "https://maculatus-rpc.x1eco.com"

CONTRACT_ADDRESS = Web3.to_checksum_address(
    "0x3db744585f892dc77750b2f4376B4Fc1Dd66d510"
)

ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "user", "type": "address"},
                    {"internalType": "uint256", "name": "nonce", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "uint8", "name": "newStatus", "type": "uint8"},
                ],
                "internalType": "struct INetworkStatus.UpdateStatusParams",
                "name": "params",
                "type": "tuple",
            },
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "updateStatus",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    }
]

w3 = Web3(Web3.HTTPProvider(RPC))
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)

# ---------------- SIGNUP ----------------


def signup(wallet):

    account = Account.from_key(wallet["private_key"])

    message = encode_defunct(text=VERIFICATION_MESSAGE)

    signed = Account.sign_message(message, wallet["private_key"])

    payload = {"address": account.address, "signature": "0x" + signed.signature.hex()}

    r = requests.post(SIGNUP_URL, json=payload, headers=HEADERS)
    data = r.json()

    if "user" not in data or "accessToken" not in data["user"]:
        print("❌ Signup failed:", data)
        return None

    print("✅ Signup success:", account.address)
    return data["user"]["accessToken"]


# ---------------- FAUCET ----------------


def request_faucet(address):

    r = requests.get(f"{FAUCET_URL}?address={address}")
    text = r.text.strip()

    if text == "ok":
        print("💧 Faucet success:", address)
        return True

    if "24 hours" in text:
        print("⚠️ Faucet already claimed:", address)
        return True


    print("❌ Faucet error:", text)
    time.sleep(60)   # ⬅️ задержка при любой другой ошибке
    return False


# ---------------- VERIFY ----------------


def verify_wallet(address, token):

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    payload = {"address": address, "chainId": CHAIN_ID}

    r = requests.post(VERIFY_URL, json=payload, headers=headers)
    data = r.json()

    if "data" not in data or "signature" not in data:
        print("❌ Verify failed:", data)
        return None, None

    print("✅ Verify success:", address)
    return data["data"], data["signature"]


# ---------------- TX (FIXED ABI SAFE) ----------------


def send_update_status(private_key, data, signature):

    account = w3.eth.account.from_key(private_key)

    params = (
        Web3.to_checksum_address(data["user"]),
        int(data["nonce"]),
        int(data["price"]),
        int(data["newStatus"]),
    )

    # 🔥 ВАЖНО: обходим contract.functions полностью
    calldata = contract.encode_abi(
        "updateStatus", args=[params, Web3.to_bytes(hexstr=signature)]
    )

    tx = {
        "to": CONTRACT_ADDRESS,
        "from": account.address,
        "data": calldata,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
        "value": int(data["price"]),
    }

    signed_tx = w3.eth.account.sign_transaction(tx, private_key)

    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    print("🚀 TX SENT:", tx_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print("✅ CONFIRMED:", receipt.transactionHash.hex())


# ---------------- RUNNER ----------------


def run():

    with open("wallets.json") as f:
        wallets = json.load(f)

    for i, wallet in enumerate(wallets[START_FROM:], start=START_FROM):

        print(f"\n========== WALLET {i} ==========")
        print(wallet["address"])

        token = signup(wallet)
        if not token:
            continue

        time.sleep(3)

        request_faucet(wallet["address"])

        time.sleep(5)

        data, signature = verify_wallet(wallet["address"], token)
        if not data:
            continue

        time.sleep(5)

        send_update_status(wallet["private_key"], data, signature)

        time.sleep(8)

        # ⬇️ ВОТ ЗДЕСЬ задержка после всех итераций
        print("⏳ All wallets processed. Sleeping 60s...")
        time.sleep(60)


if __name__ == "__main__":
    run()
