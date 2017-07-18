from ethrpc import *
from json import loads
from json import dumps

from flask import Flask
from flask import request
from flask import jsonify
from flask import Response
from settings import WALLET

import os
import time
from datetime import datetime
import hashlib

import logging
from logging.handlers import RotatingFileHandler





class passdbException(Exception):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return repr(self.value)


class passdb(object):
    def __init__(self, path=None):
        if path is not None:
            if os.path.isdir(path):
                self.path = path
                if not self.path.endswith('/'):
                    self.path = self.path + '/'
            else:
                raise passdbException('The path %s does not exist' % path)
        else:
            raise passdbException('The path can not be None')
              

    def setPassword(self, addr, password):
        if os.path.isfile(self.path + addr):
            raise passdbException('The addr: %s already exist' % addr)
        try:
            with open(self.path + addr, 'w') as f:
                f.write(password)
                f.close()
                return True
        except Exception as e:
            raise passdbException(str(e))

 
    def getPassword(self, addr):
        if os.path.isfile(self.path+addr):
            try:
                password = None
                with open(self.path + addr, 'r') as f:
                    password = f.read()
                    f.close()
                    return password
            except Exception as e:
                raise passdbException(str(e))
        else:
            raise passdbException('The addr %s does not exist'% addr)



def check_wallet(address):
    if str(address) not in WALLET['accounts'].keys():
        return None
    return {'address': address, 'passphrase': WALLET['accounts'][address]}


def currency_converter(src, dst, amount):
    conversions = {'eth': {'wei': 10 ** 18}, 'wei': {'eth': 10 ** -18}}
    return int(amount * conversions[src][dst])


def create_passphrase():
    return hashlib.sha256(os.urandom(64)).hexdigest()
    

app = Flask(__name__)
try:
    pass_dir = 'passwords'
    path = app.root_path + '/' + pass_dir
    passdb = passdb(path)
except passdbException as error:
    print error.value
    exit()

@app.route('/tx/send/', methods=["POST"])
def send_transaction():
    status = 201
    data = request.data
    try:
        content = loads(data)
    except ValueError as e:
        resp   = {'status':'error', 'message':str(e)}
        status = 400

    if not 'destination' in content :
        resp   = {'status':'error', 'message':'destination key not found'}
        status = 400

    elif not 'eth' in content:
        resp   = {'status':'error', 'message':'eth key not found'}
        status = 400

    elif not 'source' in content:
        resp   = {'status':'error', 'message':'source key not found'}
        status = 400

    wallet = check_wallet(content['source'])
    if wallet is None:
        resp   = {'status':'error', 'message':'source wallet not registered'}
        status = 400

    if status == 400:
        return Response(response=dumps(resp), status=400)


    dst  = content['destination']
    weis = currency_converter('eth', 'wei', content['eth'])
    eth = ethrpc()
    tx_dict = eth.personal_sendTransaction(wallet['address'], dst, weis, wallet['passphrase'])
    if tx_dict['status'] == 'success':
        tx   = tx_dict['result']
        resp = {'status':'success', 'result':{'source': wallet['address'], 'destination': dst, 'transaction': tx}}
        now  = time.time()
        ret  = resp['result']
        ret['timestamp'] = now
        ret['date']      = str(datetime.now())
        app.logger.info(dumps(ret))
    elif tx_dict['status'] == 'error':
        resp   = tx_dict
    return Response(response=dumps(resp), status=status)


@app.route('/wallet/balance/<string:address>/', methods=["GET"])
def get_balance(address):
    eth    = ethrpc()
    resp   = eth.eth_getBalance(address)
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/tx/info/<string:tx>/', methods=["GET"])
def get_tx_info(tx):
    eth    = ethrpc()
    resp   = eth.eth_getTransactionByHash(tx)
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/tx/receipt/<string:tx>/', methods=["GET"])
def get_tx_receipt(tx):
    eth    = ethrpc()
    resp   = eth.eth_getTransactionReceipt(tx)
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/tx/fee/<string:tx>/', methods=["GET"])
def get_tx_fee(tx):
    eth = ethrpc()
    tx_info = eth.eth_getTransactionByHash(tx)
    tx_receipt = eth.eth_getTransactionReceipt(tx)
    if tx_info['status'] == 'success' and tx_receipt['status'] == 'success':
        fee    = tx_info['result']['gasPrice'] * tx_receipt['result']['gasUsed']
        resp   = {'status':'success', 'result': fee}
        status = 200
    else:
        resp = {'status':'error', 'message':'error getting transaction information'}
        status = 503
    return Response(response=dumps(resp), status=status)


@app.route('/tx/confirmations/<string:tx>/', methods=["GET"])
def get_tx_confimations(tx):
    eth = ethrpc()
    tx_info    = eth.eth_getTransactionByHash(tx)
    print tx_info
    last_block = eth.eth_blockNumber()
    if tx_info['status'] == 'success' and last_block['status'] == 'success':
        confirmations = int(last_block['result']) - int(tx_info['result']['blockNumber'])
        resp          = {'status':'success', 'result': confirmations}
        status        = 200
    else:
        resp = {'status':'error', 'message':'error getting transaction information'}
        status = 503
    return Response(response=dumps(resp), status=status)


@app.route('/account/list/', methods=["GET"])
def get_accounts():
    eth    = ethrpc()
    resp   = eth.personal_listAccounts()
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/account/create/', methods=["GET"])
def create_account():
    passphrase = create_passphrase()
    eth    = ethrpc()
    resp   = eth.personal_newAccount(passphrase)
    if resp['status'] == 'success':
        # Crear archivo en formato: Filename = resp['result'] - Contenido: passphrase
        try:
            passdb.setPassword(resp['result'], passphrase)
            status = 200
        except passdbException as error:
            message = "create_account(): Error creating file: %s" % error.value
            resp = {'status': 'error', 'message': message}
            status = 503
    print resp
    return Response(response=dumps(resp), status=status)



@app.route('/block/last/', methods=["GET"])
def get_last_block():
    eth    = ethrpc()
    resp   = eth.eth_blockNumber()
    print resp
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/test', methods=["GET"])
def test():
    passphrase = create_passphrase()
    try:
        passdb.setPassword('0x123423414124afde123123123123', passphrase)
        status = 200
    except passdbException as error:
        message = "create_account(): Error creating file: %s" % error.value
        resp = {'status': 'error', 'message': message}
        status = 503
    resp = {'status':'success', 'result':passphrase}
    status = 200
    return Response(response=dumps(resp), status=status)



if __name__ == '__main__':
    handler = RotatingFileHandler('log/tx.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(debug=True, host='0.0.0.0', port=6969)
