import asyncio
import logging

logger = logging.getLogger(__name__)

async def retry(coro_func, *args, **kwargs):
    attempt = 0
    retries = 10
    delay = 20
    exceptions = (Exception,)
    while attempt < retries:
        try:
            return await coro_func(*args, **kwargs)
        except exceptions as e:
            attempt += 1
            if '0xe4ca4c0b' in str(e):
                logger.warning(f'Клэйм скорее всего уже был, потому что вылезла ошибка: {e}')
                raise

            if attempt >= retries:
                logger.error(f"Функция {coro_func.__name__} не удалась после {retries} попыток.")
                raise
            logger.warning(f"Ошибка в {coro_func.__name__}: {e}. Попытка {attempt}/{retries} через {delay} сек.")
            await asyncio.sleep(delay)
