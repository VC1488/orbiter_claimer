import requests
import time
import json
import os

API_KEY = ''  # Замените на ваш API ключ Arbiscan
ADDRESS = ''  # Замените на интересующий вас адрес
OUTPUT_FILE = 'data/transactions.json'
CLAIMED_FILE = 'data/claimed.txt'
SIGNATURE = '0xfa5c4e99'

BASE_URL = 'https://api.arbiscan.io/api'


def get_transactions(address, start_block=0, end_block=99999999, page=1, offset=10000, sort='asc'):
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': start_block,
        'endblock': end_block,
        'page': page,
        'offset': offset,
        'sort': sort,
        'apikey': API_KEY
    }

    try:
        response = requests.get(BASE_URL, params=params)
        data = response.json()

        if data['status'] != '1':
            print(f"Ошибка: {data['message']}")
            return []

        return data['result']

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return []


def main():
    all_transactions = []
    page = 1
    offset = 10000  # Максимальное количество записей за один запрос
    address_recorded = False  # Флаг для записи адреса только один раз

    while True:
        print(f"Получение страницы {page}...")
        transactions = get_transactions(ADDRESS, page=page, offset=offset)

        if not transactions:
            break

        all_transactions.extend(transactions)
        print(f"Получено транзакций: {len(all_transactions)}")

        # Проверка каждой транзакции на наличие сигнатуры
        for tx in transactions:
            input_data = tx.get('input', '').lower()
            if SIGNATURE in input_data:
                if not address_recorded:
                    with open(CLAIMED_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{ADDRESS}\n")
                    print(f"Сигнатура найдена. Адрес {ADDRESS} записан в {CLAIMED_FILE}")
                    address_recorded = True  # Избегаем повторной записи
                break  # Прекращаем проверку транзакций после нахождения сигнатуры

        if len(transactions) < offset:
            # Последняя страница
            break

        page += 1
        time.sleep(0.2)  # Небольшая задержка, чтобы избежать превышения лимита запросов

    # Сохранение транзакций в файл
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_transactions, f, ensure_ascii=False, indent=4)

    print(f"Все транзакции сохранены в {OUTPUT_FILE}")


if __name__ == "__main__":
    # Убедимся, что файл claimed.txt существует
    if not os.path.exists(CLAIMED_FILE):
        with open(CLAIMED_FILE, 'w', encoding='utf-8') as f:
            pass  # Создаем пустой файл

    main()
