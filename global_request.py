# global_request.py
import asyncio
from random import choice, uniform
from curl_cffi.requests import AsyncSession
from loguru import logger
import json
from pathlib import Path

TIMEOUT = [3, 10]
MAX_RETRY = 4

ERROR_CODE_EXCEPTION = -1
ERROR_CODE_FAILED_REQUEST = -2
PROXY_FILE = 'data/proxies.txt'
proxies = []

proxy_path = Path(PROXY_FILE)
if proxy_path.exists():
    with proxy_path.open('r') as f:
        proxies = [line.strip() for line in f if line.strip()]
    logger.info(f'Загружено {len(proxies)} прокси из {PROXY_FILE}')
else:
    logger.warning(f'Файл с прокси {PROXY_FILE} не найден. Продолжаем без прокси.')

async def global_request(wallet, method="get", request_retry=0, need_sleep=False, **kwargs):
    if request_retry > MAX_RETRY:
        return ERROR_CODE_FAILED_REQUEST, f"Max retries exceeded for {kwargs.get('url', 'unknown url')}"

    if 'proxy' not in kwargs or kwargs['proxy'] is None:
        if proxies:
            selected_proxy = choice(proxies)
            kwargs['proxy'] = selected_proxy
            logger.debug(f'Выбран прокси: {selected_proxy} для кошелька: {wallet}')
        else:
            kwargs['proxy'] = None

    async with AsyncSession(verify=False) as session:
        retry_count = 0

        while retry_count <= MAX_RETRY:
            try:
                if method.lower() == "post":
                    response = await session.post(**kwargs)
                elif method.lower() == "get":
                    response = await session.get(**kwargs)
                elif method.lower() == "put":
                    response = await session.put(**kwargs)
                elif method.lower() == "options":
                    response = await session.options(**kwargs)
                else:
                    logger.error(f'Неподдерживаемый HTTP метод: {method}')
                    return ERROR_CODE_FAILED_REQUEST, f'Unsupported HTTP method: {method}'

                status_code = response.status_code
                if status_code in [200, 201]:
                    timing = uniform(TIMEOUT[0], TIMEOUT[1])
                    if need_sleep:
                        await asyncio.sleep(timing)
                    try:
                        response_json = await asyncio.to_thread(response.json)
                        return status_code, response_json
                    except json.decoder.JSONDecodeError:
                        logger.info('Запрос выполнен успешно, но не содержит JSON')
                        return status_code, {}
                else:
                    if status_code == 400:
                        try:
                            response_json = await asyncio.to_thread(response.json)
                            logger.warning(f'[{wallet} - {kwargs.get("url", "")}] info: {response_json}')
                        except:
                            logger.warning(f'[{wallet} - {kwargs.get("url", "")}] info: Невозможно разобрать JSON-ответ.')
                    elif status_code == 401:
                        message = f'[{wallet} - {kwargs.get("url", "")}] Не авторизован: {status_code}'
                        logger.warning(message)
                        return 401, message
                    else:
                        try:
                            response_json = await asyncio.to_thread(response.json)
                        except:
                            response_json = 'Невозможно разобрать JSON-ответ'
                        logger.error(f'[{wallet} - {kwargs.get("url", "")}] Плохой статус код: {status_code} {response_json}')
                        if need_sleep:
                            await asyncio.sleep(30)

                    retry_count += 1
                    if retry_count > MAX_RETRY:
                        message = f'[{wallet} - {kwargs.get("url", "")}] Достигнуто максимальное количество попыток запроса'
                        logger.error(message)
                        return ERROR_CODE_FAILED_REQUEST, message
                    else:
                        if need_sleep:
                            await asyncio.sleep(1)
            except ConnectionError as error:
                logger.error(f'{wallet} - HTTPSConnectionPool - {kwargs.get("url", "")} не удалось выполнить запрос | {error}')
                if need_sleep:
                    await asyncio.sleep(25)
                return await global_request(wallet, method=method, request_retry=request_retry + 1, need_sleep=True, **kwargs)
            except Exception as error:
                logger.error(f'{wallet} - {kwargs.get("url", "")} не удалось выполнить запрос | {error}')
                if need_sleep:
                    await asyncio.sleep(10)
                return ERROR_CODE_EXCEPTION, str(error)
