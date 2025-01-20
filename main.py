import asyncio
import sys
import time
from pathlib import Path

from eth_account.messages import encode_defunct
from web3 import Web3, AsyncWeb3
from loguru import logger
from global_request import global_request
from eth_abi import abi
from retry import retry

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Инициализация AsyncWeb3
web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider("https://endpoints.omniatech.io/v1/arbitrum/one/public"))
CLAIM_ABI = [
    {
        "name": "claim",
        "type": "function",
        "inputs": [
            {"name": "userAddress", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
            {"name": "proof", "type": "bytes32[]"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    }
]

SEM_LIMIT = 1
semaphore = asyncio.Semaphore(SEM_LIMIT)

async def get_status_tx(tx_hash: str) -> int:
    logger.info(f'Проверка статуса транзакции: {tx_hash}')
    start_time_stamp = int(time.time())

    while True:
        try:
            receipt = await retry(web3.eth.get_transaction_receipt, tx_hash)
            status = receipt["status"]
            if status in [0, 1]:
                return status
        except Exception as e:
            logger.warning(f'Ошибка при получении receipt: {e}')

        current_time = int(time.time())
        if current_time - start_time_stamp > 300:
            logger.info(f'Не удалось получить статус транзакции за {300} секунд')
            return 1
        await asyncio.sleep(1)


async def sign_tx(contract_txn, key: str) -> str:
    signed_tx = web3.eth.account.sign_transaction(contract_txn, key)
    raw_tx_hash = await retry(web3.eth.send_raw_transaction, signed_tx.raw_transaction)
    tx_hash = web3.to_hex(raw_tx_hash)
    return tx_hash


async def send_tx(contract_txn, key: str):
    try:
        tx_hash = await retry(sign_tx, contract_txn, key)
        status = await retry(get_status_tx, tx_hash)
        return status
    except Exception as error:
        logger.error(f'Ошибка при отправке транзакции: {error}')
        return False, error


async def sign_message(message_text: str, key: str) -> str:
    message = encode_defunct(text=message_text)
    signed_message = web3.to_hex(
        web3.eth.account.sign_message(message, private_key=key).signature
    )
    return signed_message


async def get_merkle(address: str, key: str) -> tuple:
    message_signed = await retry(sign_message, 'Orbiter Airdrop', key)
    url = 'https://airdrop-api.orbiter.finance/airdrop/snapshot'
    headers = {
        'token': message_signed,
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        status, result = await global_request(address, method='post', url=url, headers=headers)
    except Exception as e:
        logger.error(f'Ошибка при выполнении global_request для {address}: {e}')
        return None, None

    if result.get('result') is not None:
        proof = result['result']['proof'][0]['data']
        amount = str(result['result']['proof'][0]['amount']).replace(".", "")
        return amount, proof
    else:
        return None, None


async def claim_tx(address: str, key: str, amount: str, merkle_proof: list):
    FEE_MULTIPLIER = 7.04
    amount_dec = int(amount)
    claim_contract = web3.eth.contract(
        address=Web3.to_checksum_address('0x13dfdd3a9b39323f228daf73b62c23f7017e4679'),
        abi=CLAIM_ABI
    )
    data = '0xfa5c4e99071cbb2ff029ddaf4b691745b2ba185cbe9ca2f5fa9e7358bada8fbdce764291'
    encoded_amount = abi.encode(["uint256"], [amount_dec]).hex()
    merkle_proof_bytes = [bytes.fromhex(proof[2:]) for proof in merkle_proof]
    encoded_proof = abi.encode(["bytes32[]"], [merkle_proof_bytes]).hex()
    data = data + encoded_amount + encoded_proof
    data = data.replace("0000000000000020000000000000", "0000000000000060000000000000")
    logger.debug(f'Data для транзакции: {data}')

    contract_txn = {
        'to': Web3.to_checksum_address('0x13dfdd3a9b39323f228daf73b62c23f7017e4679'),
        'data': data,
        'nonce': await web3.eth.get_transaction_count(address),
        'from': address,
        'gas': 0,  # Будет обновлено позже
        'gasPrice': int(await web3.eth.gas_price),
        'chainId': 42161,
        'value': 0,
    }

    # Оценка газа и применение множителя
    try:
        estimated_gas = await retry(web3.eth.estimate_gas,contract_txn)
        contract_txn['gas'] = int(estimated_gas * FEE_MULTIPLIER)
        logger.debug(
            f'Оценка газа: {estimated_gas}, примененный множитель: {FEE_MULTIPLIER}, итоговый газ: {contract_txn["gas"]}')
    except Exception as e:
        logger.error(f'Ошибка при оценке газа: {e}')
        return

    status = await retry(send_tx, contract_txn, key)
    if status == 1:
        logger.success(f"{address} | Успешно выполнен claim")
    else:
        logger.error(f"{address} | Транзакция не удалась")


async def process_key(key: str):
    async with semaphore:
        try:
            address = Web3.to_checksum_address(Web3().eth.account.from_key(key).address)
            logger.info(f'Обработка адреса: {address}')

            amount, merkle = await retry(get_merkle, address, key)
            if amount is not None and merkle is not None:
                logger.info(f'Начало claim для {address} с суммой {amount}')
                await retry(claim_tx, address, key, amount, merkle)
            else:
                logger.warning(f'Нет данных для claim для {address}')
        except Exception as e:
            logger.error(f'Ошибка при обработке ключа {key}: {e}')


async def load_keys(file_path: str) -> list:
    path = Path(file_path)
    if not path.exists():
        logger.error(f'Файл с приватными ключами не найден: {file_path}')
        return []
    with path.open('r') as f:
        keys = [line.strip() for line in f if line.strip()]
    logger.info(f'Загружено {len(keys)} приватных ключей')
    return keys


async def main():
    keys = await load_keys('data/private_keys.txt')
    if not keys:
        logger.error('Нет приватных ключей для обработки')
        return

    tasks = [asyncio.create_task(process_key(key)) for key in keys]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())