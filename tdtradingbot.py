import requests
import urllib
import time
from splinter import Browser
import numpy as np 
import pandas as pd
from datetime import datetime, timedelta
from configparser import ConfigParser
import threading

config = ConfigParser()
config.add_section('auth')
config.read('config.ini')

API_KEY = 'GET FROM https://developer.tdameritrade.com/'
PASSWORD = 'your td ameritrade pass'
USERNAME = 'your td ameritrade user'
REDIRECT_URL = 'GET FROM https://developer.tdameritrade.com/'
executable_path = {'executable_path':r'path of your chrome driver for auto authentication'}

if not config.get('auth','refresh_token', fallback = False):
    browser = Browser('chrome', **executable_path, headless=False)
    request_url = fr'https://auth.tdameritrade.com/auth?response_type=code&redirect_uri={REDIRECT_URL}&client_id={API_KEY}%40AMER.OAUTHAP'
    browser.visit(request_url)
    payload = {'username': USERNAME,
               'password': PASSWORD}

    # fill out each part of the form and click submit
    username = browser.find_by_id("username0").first.fill(payload['username'])
    password = browser.find_by_id("password1").first.fill(payload['password'])
    submit   = browser.find_by_id("accept").first.click()


    time.sleep(1)
    browser.find_by_text('Can\'t get the text message?').first.click()

    # Get the Answer Box
    browser.find_by_value("Answer a security question").first.click()

    # Answer the Security Questions.
    if browser.is_text_present('Security Question 1'):
        browser.find_by_id('secretquestion0').first.fill('1')

    elif browser.is_text_present('Security Question 2'):
        browser.find_by_id('secretquestion0').first.fill('answer 2')

    elif browser.is_text_present('Security Question 3'):
        browser.find_by_id('secretquestion0').first.fill('answer 3')

    elif browser.is_text_present('Security Question 4'):
        browser.find_by_id('secretquestion0').first.fill('answer 4')

    # Submit results
    browser.find_by_id('accept').first.click()
    time.sleep(2)
    browser.find_by_xpath('/html/body/form/main/fieldset/div/div[1]/label').first.click()
    browser.find_by_id('accept').first.click()
    browser.find_by_id('accept').first.click()

    # grab the part we need, and decode it.
    new_url = browser.url
    parse_url = urllib.parse.unquote(new_url.split('code=')[1])

    # close the browser
    browser.quit()
    url = r"https://api.tdameritrade.com/v1/oauth2/token"

    # define the headers
    headers = {"Content-Type":"application/x-www-form-urlencoded"}

    # define the payload
    payload = {'grant_type': 'authorization_code', 
               'access_type': 'offline', 
               'code': parse_url, 
               'client_id': API_KEY, 
               'redirect_uri':'http://localhost/test'}

    # post the data to get the token
    authReply = requests.post(r'https://api.tdameritrade.com/v1/oauth2/token', headers = headers, data=payload)

    # convert it to a dictionary
    decoded_content = authReply.json()
    access_token = decoded_content['access_token']
    refresh_token = decoded_content['refresh_token']
    config.set('auth', 'REFRESH_TOKEN', refresh_token)
    config.set('auth', 'ACCESS_TOKEN', access_token)
    with open(file='config.ini', mode='w') as f:
        config.write(f)

refresh_token = config.get('auth', 'refresh_token')

def checkPosition(symbol:str) -> bool:
    for position in positions_list:
        if(position['instrument']['symbol'] == symbol):
            return True
    return False

def refreshToken():
    refreshurl = r'https://api.tdameritrade.com/v1/oauth2/token'
    # define the headers
    headers = {"Content-Type":"application/x-www-form-urlencoded"}

    # define the payload
    payload = {'grant_type': 'refresh_token',
               'refresh_token': refresh_token,
               'client_id': API_KEY}

    refreshReply = requests.post(r'https://api.tdameritrade.com/v1/oauth2/token', headers = headers, data=payload)
    refreshReply = refreshReply.json()
    global access_token 
    access_token = refreshReply['access_token']
    print('Token has been refreshed')
    
def isMarketOpen():
    #check if market is open
    currenttime = (datetime.now()+timedelta(hours=3)).isoformat()
    marketopenurl = r'https://api.tdameritrade.com/v1/marketdata/EQUITY/hours'
    payload = {'apikey': API_KEY, 
               'date': currenttime}
    marketopendata = requests.get(marketopenurl, headers = headers, params = payload)
    marketopendata = marketopendata.json()
    isOpen = marketopendata['equity']['EQ']['isOpen']
    regClose = marketopendata['equity']['EQ']['sessionHours']['regularMarket'][0]['end']
    regOpen = marketopendata['equity']['EQ']['sessionHours']['regularMarket'][0]['start']
    regMarketOpen = currenttime>regOpen and currenttime<regClose
    return regMarketOpen

#you can replace this with your own trading algorithm    
def setUpBuyLoop(symbol):
    print(symbol)
    while isMarketOpen():
        refreshToken()
        pricehistoryurl = fr'https://api.tdameritrade.com/v1/marketdata/{symbol}/pricehistory'
        payload = {'apikey': API_KEY, 
                   'periodType': 'year', 
                   'period': '1', 
                   'frequencyType': 'daily', 
                   'frequency':'1',
                   'needExtendedHoursData': 'false'}
        pricedata = requests.get(pricehistoryurl, headers = headers, params = payload )


        pricedata = pricedata.json()
        columns = ['datetime', 'high','low','open', 'close', 'volume','ema','7candlelow', '7candlehigh']
        pricedataframe = pd.DataFrame(columns=columns)
        for candle in pricedata['candles']:
            pricedataframe = pricedataframe.append(
                                                pd.Series([candle['datetime'], 
                                                           candle['high'], 
                                                           candle['low'], 
                                                           candle['open'],
                                                           candle['close'],
                                                           candle['volume'],
                                                          0, 0, 0], 
                                                          index = columns), 
                                                ignore_index = True)
            pricedataframe['ema'] = pricedataframe['close'].transform(lambda x:x.ewm(span=200, adjust=False).mean())

            pricedataframe['7candlelow'] = pricedataframe['close'].rolling(window=7).min()
            pricedataframe['7candlehigh'] = pricedataframe['close'].rolling(window=7).max()



        recentClose = pricedataframe['close'].iloc[-1]
        recent200EMA = pricedataframe['ema'].iloc[-1]
        recent7CandleLow = pricedataframe['7candlelow'].iloc[-2]
        recent7CandleHigh = pricedataframe['7candlehigh'].iloc[-2]

        #calculate the atr for the past 14 days
        high_low = pricedataframe['high'] - pricedataframe['low']
        high_close = np.abs(pricedataframe['high'] - pricedataframe['close'].shift())
        low_close = np.abs(pricedataframe['low'] - pricedataframe['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(14).sum()/14
        buyurl = fr'https://api.tdameritrade.com/v1/accounts/{account_id}/orders'
    

        if(recentClose > recent200EMA and recentClose <= recent7CandleLow and not checkPosition(symbol)):
            print('buy '+symbol)
            stopPrice = recentClose - 2* atr.iloc[-1]
            stopPrice = round(stopPrice, 2)
            #this json order doesn't work still :(
            orderpayload = {
              "orderType": "MARKET",
              "session": "NORMAL",
              "duration": "DAY",
              "orderStrategyType": "TRIGGER",
              "orderLegCollection": [
                {
                  "instruction": "BUY",
                  "quantity": 1,
                  "instrument": {
                    "symbol": symbol,
                    "assetType": "EQUITY"
                  }
                }
              ],
              "childOrderStrategies": [
                {
                  "orderType": "STOP",
                  "session": "NORMAL",
                  "stopPrice": stopPrice,
                  "duration": "DAY",
                  "orderStrategyType": "SINGLE",
                  "orderLegCollection": [
                    {
                      "instruction": "SELL",
                      "quantity": 1,
                      "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                      }
                    }
                  ]
                }
              ]
            }
            orderstop ={
                  "orderType": "STOP",
                  "session": "NORMAL",
                  "stopPrice": stopPrice,
                  "duration": "DAY",
                  "orderStrategyType": "SINGLE",
                  "orderLegCollection": [
                    {
                      "instruction": "SELL",
                      "quantity": 1,
                      "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                      }
                    }
                  ]
                }
            payload = {
              "orderType": "MARKET",
              "session": "NORMAL",
              "duration": "DAY",
              "orderStrategyType": "SINGLE",
              "orderLegCollection": [
                {
                  "instruction": "Buy",
                  "quantity": 1,
                  "instrument": {
                    "symbol": symbol,
                    "assetType": "EQUITY"
                  }
                }
              ]
            }



            header = {'Authorization':"Bearer {}".format(access_token),
                      "Content-Type":"application/json"}
            orderreq = requests.post(buyurl, headers = header, json = payload )
            time.sleep(120)
            orderstopreq = requests.post(buyurl, headers = header, json = orderstop)
            print(orderstopreq.status_code)
            

        elif(recentClose >= recent7CandleHigh and checkPosition(symbol)):
            print('sell '+symbol)
            orderpayload = {
                    "orderType": "MARKET",
                    "session": "NORMAL",
                    "duration": "DAY",
                    "orderStrategyType": "SINGLE",
                    "orderLegCollection": [{
                        "instruction": "SELL",
                        "quantity": 1,
                        "instrument": {
                            "symbol": symbol,
                            "assetType": "EQUITY"
                        }
                    }]
                }
            header = {'Authorization':"Bearer {}".format(access_token),
                      "Content-Type":"application/json"}
            orderreq = requests.post(buyurl, headers = header, json = orderpayload )
            print(orderreq.status_code)
        time.sleep(15*60)
        print('looped')
        
    print('closed')

refreshToken()


url = r'https://api.tdameritrade.com/v1/accounts'
headers = {'Authorization': "Bearer {}".format(access_token)}
payload = {'fields':['positions']}
account_info = requests.get(url, headers = headers, params = payload )
account_info = account_info.json()
account_id = account_info[0]['securitiesAccount']['accountId']
positions_list = account_info[0]['securitiesAccount']['positions']

#select the stocks you want to trade
threading.Thread(target=setUpBuyLoop, args=['AAPL']).start()
threading.Thread(target=setUpBuyLoop, args=['BABA']).start()
threading.Thread(target=setUpBuyLoop, args=['MSFT']).start()
threading.Thread(target=setUpBuyLoop, args=['KLIC']).start()