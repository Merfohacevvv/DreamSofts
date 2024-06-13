import aiohttp
import asyncio
import requests
import re
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Реализация асинхронного сеанса запросов с повторами
async def aiohttp_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    async def on_request_error(request, exception, traces):
        print(f'Request failed: {request.url} - Exception: {exception}')

    retry_options = aiohttp.RetryOptions(
        attempts=retries,
        factor=backoff_factor,
        statuses=status_forcelist,
        exceptions={aiohttp.ClientError},
        raise_for_status=False,
        max_timeout=300,
        on_error=on_request_error
    )
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector()
    session = aiohttp.ClientSession(retry_options=retry_options, timeout=timeout, connector=connector)
    return session


# Асинхронный запрос текущей цены валюты
async def get_current_price_async(coin_id, currency="usd"):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": currency}
    async with aiohttp_retry_session() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                price_data = await response.json()
                return price_data.get(coin_id, {}).get(currency, None)
            print(f"Error fetching price for {coin_id}. Status: {response.status}")
            return None


# Кэширование возраста кошельков
wallet_age_cache = {}


# Асинхронная функция для получения возраста кошелька
async def get_wallet_age_async(api_key, wallet_address):
    if wallet_address in wallet_age_cache:
        return wallet_age_cache[wallet_address]

    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet_address,
        "page": 1,
        "offset": 1,
        "sort": "asc",
        "apikey": api_key
    }
    async with aiohttp_retry_session() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                transactions = await response.json()
                if transactions['result']:
                    first_tx = transactions['result'][0]
                    first_tx_date = datetime.fromtimestamp(int(first_tx['timeStamp']))
                    wallet_age = (datetime.now() - first_tx_date).days
                    wallet_age_cache[wallet_address] = wallet_age
                    return wallet_age
                else:
                    wallet_age_cache[wallet_address] = 0
                    return 0  # If no transactions found, consider age as 0
            print(f"Failed to fetch transactions for {wallet_address}. Status: {response.status}")
            return None


# Изменения позволят ускорить выполнение запросов и сократить количество повторных операций благодаря кэшированию.

def requests_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504), session=None):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def get_current_price(coin_id, currency="usd"):
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": currency
    }
    response = requests.get(url, params=params)
    try:
        price_data = response.json()
        price = price_data[coin_id][currency]
        return price
    except KeyError as e:
        print(f"Error processing data for {coin_id}: {e}")
        print("Response data:", response.json())
        return None


def fetch_transactions(api_key, contract_address):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract_address,
        "page": 1,
        "offset": 100,
        "sort": "desc",
        "apikey": api_key
    }
    response = requests.get(url, params=params)
    transactions = response.json()
    return transactions['result']


def get_wallet_age(api_key, wallet_address):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet_address,
        "page": 1,
        "offset": 1,
        "sort": "asc",
        "apikey": api_key
    }
    try:
        response = requests_retry_session().get(url, params=params)
        transactions = response.json()
        if transactions['result']:
            first_tx = transactions['result'][0]
            first_tx_date = datetime.fromtimestamp(int(first_tx['timeStamp']))
            wallet_age = (datetime.now() - first_tx_date).days
            return wallet_age
        return 0  # If no transactions found, consider age as 0
    except Exception as x:
        print('It failed :(', x.__class__.__name__)
        return None  # In case of error, return None to indicate failure


def filter_wallet_addresses(api_key, transactions, current_price, min_age=100, min_transaction_value_usd=2000):
    wallet_addresses = set()  # Используем set для хранения уникальных адресов
    for tx in transactions:
        if tx['to'] and tx['value'] != '0':  # Проверяем, что 'to' адрес присутствует и транзакция не нулевая
            if not is_contract_address(api_key, tx['to']):  # Проверяем, что адрес не является контрактом
                age = get_wallet_age(api_key, tx['to'])
                if age >= min_age:
                    value_in_eth = int(tx['value']) / 10 ** int(tx['tokenDecimal'])  # Конвертируем из Wei в ETH
                    value_in_usd = value_in_eth * current_price  # Переводим в USD

                    if value_in_usd > min_transaction_value_usd:  # Условие теперь на превышение минимальной суммы
                        wallet_addresses.add(tx['to'])  # Добавляем адрес в набор
    return list(wallet_addresses)  # Возвращаем список уникальных адресов


# ВОЗМОЖНО УДАЛИТЬ ontains_swap_keyword и filter_wallet_addresses_full
def contains_swap_keyword(transaction):
    # Define the fields to search for the "swap" keyword
    fields_to_check = ['from', 'to', 'input', 'tokenName', 'methodName']

    # Check each field if it exists in the transaction and if it contains "swap"
    for field in fields_to_check:
        if field in transaction and re.search(r'swap', str(transaction[field]), re.IGNORECASE):
            return True
    return False


def get_historical_price(date, coin_id):
    url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/history'
    params = {'date': date.strftime('%d-%m-%Y')}
    response = requests.get(url, params=params)
    data = response.json()
    return data['market_data']['current_price']['usd']


def get_transactions_wallet(address, api_key, contract_address):
    url = f'https://api.etherscan.io/api'
    params = {
        'module': 'account',
        'action': 'tokentx',
        'address': address,
        'contractaddress': contract_address,
        'startblock': 0,
        'endblock': 99999999,
        'sort': 'asc',
        'apikey': api_key
    }
    response = requests.get(url, params=params)
    return response.json()


def calculate_pnl(address, api_key, coin_id, contract_address, current_price):
    d = {int(a): 0 for a in range(32)}
    transactions = get_transactions_wallet(address, api_key, contract_address)
    total_bought_7, total_bought_14 = 0, 0
    total_sold_7, total_sold_14 = 0, 0
    buy_amount_7, buy_amount_14 = 0, 0
    sell_amount_7, sell_amount_14 = 0, 0

    for tx in transactions['result']:
        timestamp = int(tx['timeStamp'])
        tokenDecimal = int(tx['tokenDecimal'])
        date = datetime.utcfromtimestamp(timestamp)
        current_date = datetime.today()
        result = current_date - date
        x = int(date.day)

        if result.days <= 7:

            if date.day == current_date.day:
                price = current_price
            elif d[x] != 0:
                price = d[x]
            else:

                price = get_historical_price(date, coin_id)
                d[x] = price
            amount = int(tx['value']) / 10 ** tokenDecimal

            if tx['to'].lower() == address.lower():
                total_bought_7 += amount
                buy_amount_7 += amount * price
            elif tx['from'].lower() == address.lower():
                total_sold_7 += amount
                sell_amount_7 += amount * price

        if result.days <= 14:
            if date.day == current_date.day:
                price = current_price
            elif d[x] != 0:
                price = d[x]
            else:
                price = get_historical_price(date, coin_id)
                d[x] = price
            amount = int(tx['value']) / 10 ** tokenDecimal

            if tx['to'].lower() == address.lower():
                total_bought_14 += amount
                buy_amount_14 += amount * price
            elif tx['from'].lower() == address.lower():
                total_sold_14 += amount
                sell_amount_14 += amount * price

    current_balance_7 = total_bought_7 - total_sold_7
    current_value_7 = current_balance_7 * current_price

    total_invested_7 = buy_amount_7
    total_received_7 = sell_amount_7 + current_value_7

    current_balance_14 = total_bought_14 - total_sold_14
    current_value_14 = current_balance_14 * current_price

    total_invested_14 = buy_amount_14
    total_received_14 = sell_amount_14 + current_value_14

    pnl_7 = total_received_7 - total_invested_7
    pnl_14 = total_received_14 - total_invested_14

    return pnl_7, pnl_14
def is_contract_address(api_key, address):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key
    }
    try:
        response = requests_retry_session().get(url, params=params)
        data = response.json()
        if data['result'][0]['ContractName'] != '':  # Если результат не '',то адрес является контрактом
            return True
        return False
    except Exception as x:
        print('Failed to check contract address:', x.__class__.__name__)
        return False


def main():
    api_key = "BCFXU4RJNNJRNUQN894XKSSEJCAC5SS3Q1"
    contract_address = "0xd38bb40815d2b0c2d2c866e0c72c5728ffc76dd9"
    coin_id = "symbiosis-finance"

    current_price = get_current_price(coin_id)  # Убедитесь, что это возвращает float
    print('Current price token:', coin_id, '=', current_price)
    if current_price is None:
        print("Failed to fetch current price.")
        return

    transactions = fetch_transactions(api_key, contract_address)
    wallet_addresses = filter_wallet_addresses(api_key, transactions, current_price)


    print("Wallet addresses with transactions over $2000:")
    for address_wallet in wallet_addresses:
        print(address_wallet)
        pnl_7, pnl_14 = calculate_pnl(address_wallet, api_key, coin_id, contract_address, current_price)
        print('PnL за 7 дней:', int(pnl_7), "USD")
        print('PnL за 14 дней:', int(pnl_14), "USD")
    # pnl_7, pnl_14 = calculate_pnl('0x20a3a4ae2aacb8bbcfd89dc71280dd18cd9a0cb4', api_key, coin_id, contract_address, current_price)
    # print('PnL за 7 дней:', int(pnl_7), "USD")
    # print('PnL за 14 дней:', int(pnl_14), "USD")



main()  # Now this line will execute the main function
