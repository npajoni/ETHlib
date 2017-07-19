from ethrpc import *
from json import loads
from json import dumps

from flask import Flask
from flask import request
from flask import jsonify
from flask import Response

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


def currency_converter(src, dst, amount):
    conversions = {'eth': {'wei': 10 ** 18}, 'wei': {'eth': 10 ** -18}}
    return float(amount * conversions[src][dst])


def create_passphrase():
    return hashlib.sha256(os.urandom(64)).hexdigest()


def discount_fee(src, dst, weis):
    eth    = ethrpc()
    resp   = eth.eth_estimateGas(dst, src, weis)
    if resp['status'] == 'success':
        tx_amount = weis - resp['result']
        result = {'amount': tx_amount, 'fee': resp['result']}
        return {'status':'success', 'result': result}
    else:
        return resp


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

    if not 'weis' in content:
        resp   = {'status':'error', 'message':'weis key not found'}
        status = 400

    if not 'source' in content:
        resp   = {'status':'error', 'message':'source key not found'}
        status = 400

    if not 'inc_fee' in content:
        resp   = {'status':'error', 'message':'inc_fee key not found'}
        status = 400

    try:
        src = content['source']
        passphrase = passdb.getPassword(src)
    except passdbException as error:
        message = 'Error getting wallet password: %s' % error.value
        resp   = {'status':'error', 'message':'source wallet not registered'}
        status = 400

    if status == 400:
        return Response(response=dumps(resp), status=status)

    dst  = content['destination']
    weis = content['weis']
    if inc_fee:
        resp = discount_fee(src, dst, weis)
        if resp['status'] == 'success':
            weis = resp['result']['amount']
            fee  = resp['result']['fee']
        else:
            return Response(response=dumps(resp), status=status)
    else:
        fee = 0

    eth = ethrpc()
    tx_dict = eth.personal_sendTransaction(src, dst, weis, passphrase)

    if tx_dict['status'] == 'success':
        tx   = tx_dict['result']
        result = {'source': src, 'destination': dst, 'transaction': tx, 'weis': weis, 'fee': fee}
        resp = {'status':'success', 'result':result}
        now  = time.time()
        ret  = resp['result']
        ret['timestamp'] = now
        ret['date']      = str(datetime.now())
        app.logger.info(dumps(ret))
    elif tx_dict['status'] == 'error':
        resp   = tx_dict

    return Response(response=dumps(resp), status=status)


@app.route('/tx/send2', methods=["POST"])
def send_transaction_2():
    status = 201
    data = request.data
    # Verifico valores del JSON
    try:
        content = loads(data)
    except ValueError as e:
        resp   = {'status':'error', 'message':str(e)}
        status = 400

    if not 'destination' in content :
        resp   = {'status':'error', 'message':'destination key not found'}
        status = 400

    if not 'weis' in content:
        resp   = {'status':'error', 'message':'weis key not found'}
        status = 400

    if not 'source' in content:
        resp   = {'status':'error', 'message':'source key not found'}
        status = 400

    if not 'inc_fee' in content:
        resp   = {'status':'error', 'message':'inc_fee key not found'}
        status = 400

    # Desbloqueo cuenta
    try:
        src = content['source']
        passphrase = passdb.getPassword(src)
    except passdbException as error:
        message = 'Error getting wallet password: %s' % error.value
        resp   = {'status':'error', 'message':'source wallet not registered'}
        return Response(response=dumps(resp), status=status)
    eth  = ethrpc()
    unlock = eth.personal_unlockAccount(src, passphrase)
    if unlock['status'] == 'success':
        if not unlock['result']:
            resp   = {'status':'error', 'message':'account could not be unlocked'}
            status = 400
    else:
        resp   = unlock
        status = 400

    # Retorno ante algun error
    if status == 400:
        return Response(response=dumps(resp), status=status)

    dst  = content['destination']
    weis = content['weis']
    if inc_fee:
        resp = discount_fee(src, dst, weis)
        if resp['status'] == 'success':
            weis = resp['result']['amount']
            fee  = resp['result']['fee']
        else:
            return Response(response=dumps(resp), status=status)
    else:
        fee = 0

    if 'gas' in content:
        gas = content['gas']
    else:
        gas = None

    if 'gas_price' in content:
        gas_price = content['gas_price']
    else:
        gas_price = None

    eth = ethrpc()
    tx_dict = eth.eth_sendTransaction(src, dst, weis, gas, gas_price)

    if tx_dict['status'] == 'success':
        tx   = tx_dict['result']
        result = {'source': src, 'destination': dst, 'transaction': tx, 'gas': gas, 'gas_price': gas_price, 'weis': weis, 'fee': fee}
        resp = {'status':'success', 'result':result}
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


@app.route('/tx/estimatefee/<string:address>/', methods=["GET"])
def get_tx_estimate_fee(address):
    eth          = ethrpc()
    gas_price    = eth.eth_gasPrice()
    gas_estimate = eth.eth_estimateGas(address)
    if gas_price['status'] == 'success' and gas_estimate['status'] == 'success':
        fee    = gas_price['result'] * gas_estimate['result']
        resp   = {'status':'success', 'result': fee}
        status = 200
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
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/gas/price/', methods=["GET"])
def get_gas_price():
    eth    = ethrpc()
    resp   = eth.eth_gasPrice()
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/gas/estimate/<string:address>', methods=["GET"])
def get_gas_estimate(address):
    eth    = ethrpc()
    resp   = eth.eth_estimateGas(address)
    status = 200
    return Response(response=dumps(resp), status=status)


@app.route('/test/<string:address>', methods=["GET"])
def test(address):
    #resp = discount_fee('0x1586da20defcc011356aa934cf35c1031fa90871', '0xf4E1D94C990F470E231Aa38bcc0178C1Ca9A02Ec', 20000000000000000)
    eth = ethrpc()
    resp = eth.personal_lockAccount(address)
    status = 200
    return Response(response=dumps(resp), status=status)



if __name__ == '__main__':
    handler = RotatingFileHandler('log/tx.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(debug=True, host='0.0.0.0', port=6969)
