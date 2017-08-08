from lib.ethrpc import *
from json import loads
from json import dumps

from flask import Flask
from flask import request
from flask import jsonify
from flask import Response

import os
import socket
import time
from datetime import datetime
import hashlib
from keys import S3
from lib.s3 import *


import logging
from logging.handlers import RotatingFileHandler


#########################################################################################
#           Clase y funciones para generacion y obetencion de passphrases               #
#########################################################################################


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
        except Exception as e:
            raise passdbException(str(e))

        # Upload to S3 Bucket
        s3 = AwsS3(S3['access_key'], S3['secret_key'])
        if os.path.isfile(self.path + addr):
            try:
                s3.upload(self.path, addr, S3['bucket'], S3['path'])
                return True
            except AwsS3Exception as e:
                raise passdbException(str(e))
        else:
            raise passdbException('File does not exist: %s%s' % (path, addr))


    def getPassword(self, addr):
        if not os.path.isfile(self.path+addr):
            s3 = AwsS3(S3['access_key'], S3['secret_key'])
            try:
                s3path = S3['path'] + addr
                print "downloading key %s" % addr
                s3.download(S3['bucket'], s3path, self.path, addr)
            except AwsS3Exception as error:
                raise passdbException('The addr %s does not exist and could not be downloaded from S3'% addr)

        try:
            password = None
            with open(self.path + addr, 'r') as f:
                password = f.read()
                f.close()
                return password
        except Exception as e:
            raise passdbException(str(e))


def create_passphrase():
    return hashlib.sha256(os.urandom(64)).hexdigest()


def discount_fee(src, dst, weis, gas_price=None):
    # Obtengo el gas usado estimado para la transaccion
    gas_used = eth.eth_estimateGas(dst, src, weis)
    if gas_used['status'] != 'success':
        return gas_used
    # Si no esta definido el gas price, obtengo el gas price de la red
    if gas_price is None:
        resp = eth.eth_gasPrice()
        if resp['status'] == 'success':
            gas_price = resp['result']
        else:
            return resp
    fee = int(gas_used['result']) * int(gas_price)
    # Calculo el monto a transferir sin el fee
    tx_amount = weis - fee
    result = {'weis': tx_amount, 'fee': fee, 'gas':gas_used['result'], 'gas_price':gas_price}
    return {'status':'success', 'result': result}


# Devuelve True o False si pudo o no desbloquear la cuenta
def unlock_account(address):
    # Obtengo el password de la cuenta especificada
    try:
        passphrase = passdb.getPassword(address)
    except passdbException as error:
        message = 'Error getting wallet password: %s' % error.value
        resp   = {'status':'error', 'message': message}
        return resp
    # Desbloqueo la cuenta
    resp = eth.personal_unlockAccount(address, passphrase)
    if resp['status'] == 'success':
        if not resp['result']:
            resp   = {'status':'error', 'message':'account could not be unlocked'}

    return resp


# Devuelve True o False si puedo o no bloquear la cuenta
def lock_account(address):
    resp = eth.personal_lockAccount(address)
    if resp['status'] == 'success':
        if not resp['result']:
            resp   = {'status':'error', 'message':'account could not be unlocked'}

    return resp


#########################################################################################
#                               Inicializacion de Variables                             #
#########################################################################################
ethgw = Flask(__name__)
try:
    #pass_dir = 'passwords'
    #path = ethgw.root_path + '/' + pass_dir
    path = '/var/ethgw/passwords'
    passdb = passdb(path)
except passdbException as error:
    print error.value
    exit()

eth = ethrpc()


#########################################################################################
#                              Funciones y URLs de Flask                                #
#########################################################################################
# Devuelve True si el nodo esta escuchando por conecciones de la red
@ethgw.route('/net/listening/', methods=["GET"])
@ethgw.route('/net/listening', methods=["GET"])
def net_listening():
    resp   = eth.net_listening()
    status = 200
    return Response(response=dumps(resp), status=status)

# Devuelve la cantindad de peers conectados al node
@ethgw.route('/net/peercount/', methods=["GET"])
@ethgw.route('/net/peercount', methods=["GET"])
def net_peer_count():
    try:
        resp   = eth.net_peerCount()
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
        print resp
    return Response(response=dumps(resp), status=status)

# Envia transaccion al nodo utilizando el metodo eth y devuelve la TX si es exitosa
@ethgw.route('/tx/send/', methods=["POST"])
@ethgw.route('/tx/send', methods=["POST"])
def send_transaction():
    # Parametros madatorios
    mdt_params = ['destination', 'weis', 'source', 'inc_fee']
    # Parametros opcionales
    opt_params = ['gas', 'gas_price']
    # Cargo el contenido del POST
    try:
        content = loads(request.data)
    except ValueError as e:
        resp   = {'status':'error', 'message':str(e)}
        return Response(response=dumps(resp), status=400)

    # Verifico parametros mandatorios
    for param in mdt_params:
        if not param in content :
            msg    = "%s key not found" % param 
            resp   = {'status':'error', 'message':' msg'}
            return Response(response=dumps(resp), status=400)

    # Cargo parametros opcionales o asigno None si no fueron definidos
    for param in opt_params:
        if param not in content:
            content[param] = None

    # Desbloqueo cuenta
    resp = unlock_account(content['source'])
    if resp['status'] == 'error':
        return Response(response=dumps(resp), status=503)

    # Si el monto incluye fee, se lo descuento antes de transferir
    if content['inc_fee']:
        resp = discount_fee(content['source'], content['destination'], content['weis'], content['gas_price'])
        if resp['status'] == 'success':
            content['weis']      = resp['result']['weis']
            fee                  = resp['result']['fee']
            if content['gas'] is None:
                content['gas'] = resp['result']['gas']
            if content['gas_price'] is None:
                content['gas_price'] = resp['result']['gas_price']
            

        else:
            return Response(response=dumps(resp), status=503)
    else:
        fee = 0

    # Envio transaccion al nodo
    try:
        resp = eth.eth_sendTransaction(content['source'], content['destination'], content['weis'],
                                       content['gas'], content['gas_price'])
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503

    # Bloqueo la cuenta
    lock_account(content['source'])

    if resp['status'] == 'success':
        result = {'source': content['source'], 'destination': content['destination'], 
                  'transaction': resp['result'], 'gas': content['gas'], 'gas_price': content['gas_price'],
                  'weis': content['weis'], 'fee': fee}

        resp = {'status':'success', 'result':result}
        now  = time.time()
        ret  = resp['result']
        ret['timestamp'] = now
        ret['date']      = str(datetime.now())
        ethgw.logger.info(dumps(ret))
        status = 201

    return Response(response=dumps(resp), status=status)


# Devuelve el balance de la wallet pasada como argumento
@ethgw.route('/wallet/balance/<string:address>/', methods=["GET"])
@ethgw.route('/wallet/balance/<string:address>', methods=["GET"])
def get_balance(address):
    try:
        resp   = eth.eth_getBalance(address)
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve data de la tx pasada como argumento
@ethgw.route('/tx/hash/<string:tx>/', methods=["GET"])
@ethgw.route('/tx/hash/<string:tx>', methods=["GET"])
def get_tx_info(tx):
    try:
        resp   = eth.eth_getTransactionByHash(tx)
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve data de la tx pasada como argumento
@ethgw.route('/tx/receipt/<string:tx>/', methods=["GET"])
@ethgw.route('/tx/receipt/<string:tx>', methods=["GET"])
def get_tx_receipt(tx):
    try:
        resp   = eth.eth_getTransactionReceipt(tx)
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve el fee de la tx pasada como argumento
@ethgw.route('/tx/fee/<string:tx>/', methods=["GET"])
@ethgw.route('/tx/fee/<string:tx>', methods=["GET"])
def get_tx_fee(tx):
    try:
        tx_info    = eth.eth_getTransactionByHash(tx)
        tx_receipt = eth.eth_getTransactionReceipt(tx)
        if tx_info['status'] == 'success' and tx_receipt['status'] == 'success':
            fee    = tx_info['result']['gasPrice'] * tx_receipt['result']['gasUsed']
            resp   = {'status':'success', 'result': fee}
            status = 200
        else:
            resp = {'status':'error', 'message':'error getting transaction information'}
            status = 503
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve la cantidad de confirmaciones de la tx pasada como argumento
@ethgw.route('/tx/confirmations/<string:tx>/', methods=["GET"])
@ethgw.route('/tx/confirmations/<string:tx>', methods=["GET"])
def get_tx_confimations(tx):
    try:
        tx_info    = eth.eth_getTransactionByHash(tx)
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
        return Response(response=dumps(resp), status=status)

    if tx_info['status'] == 'success':
        if  tx_info['result']['blockNumber'] is None:
            confirmations = 0
            resp          = {'status':'success', 'result': confirmations}
            status        = 200
        else:
            last_block = eth.eth_blockNumber()
            if last_block['status'] == 'success':
                confirmations = int(last_block['result']) - int(tx_info['result']['blockNumber'])
                resp          = {'status':'success', 'result': confirmations}
                status        = 200
            else:
                resp = {'status':'error', 'message':'error getting transaction information'}
                status = 503
    else:
        resp   = tx_info
        status = 503

    return Response(response=dumps(resp), status=status)


# Devuelve el fee estimado de la transaccion generada con los datos del json
@ethgw.route('/tx/estimatefee/', methods=["POST"])
@ethgw.route('/tx/estimatefee', methods=["POST"])
def get_tx_estimate_fee():
    # Parametros madatorios
    mdt_params = ['destination']
    # Parametros opcionales
    opt_params = ['source', 'weis']

    # Cargo el contenido del POST
    try:
        content = loads(request.data)
    except ValueError as e:
        resp   = {'status':'error', 'message':str(e)}
        return Response(response=dumps(resp), status=400)

    # Verifico parametros mandatorios
    for param in mdt_params:
        if not param in content :
            msg    = "%s key not found" % param 
            resp   = {'status':'error', 'message':' msg'}
            return Response(response=dumps(resp), status=400)

    # Cargo en None los paramtros opcionales si no fueron definidos
    for param in opt_params:
        if param not in content:
            content[param] = None

    if 'gas_price'not  in content:
        try:
            resp = eth.eth_gasPrice()
            if resp['status'] == 'success':
                content['gas_price'] = resp['result']
            else:
                return Response(response=dumps(resp), status=503)
        except socket.error as error:
            msg    = "ethrpc(): %s" % str(error)
            resp   = {'status':'error', 'message':msg}
            status = 503
            return Response(response=dumps(resp), status=status)

    # Devuelvo la cantidad de gas a utilizar estimada
    try:
        gas_estimate = eth.eth_estimateGas(content['destination'], content['source'], content['weis'])
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)

    if gas_estimate['status'] == 'success':
        fee    = content['gas_price'] * gas_estimate['result']
        resp   = {'status':'success', 'result': fee}
        status = 200
    else:
        resp = {'status':'error', 'message':'error getting transaction information'}
        status = 503

    return Response(response=dumps(resp), status=status)


# Devuelve el listado de cuentas disponibles en el nodo
@ethgw.route('/account/list/', methods=["GET"])
@ethgw.route('/account/list', methods=["GET"])
def get_accounts():
    try:
        resp   = eth.personal_listAccounts()
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Crea una cuenta en el nodo y devuelve su address
@ethgw.route('/account/create/', methods=["GET"])
@ethgw.route('/account/create', methods=["GET"])
def create_account():
    passphrase = create_passphrase()
    try:
        resp   = eth.personal_newAccount(passphrase)
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503

    if resp['status'] == 'success':
        # Crear archivo en formato: Filename = resp['result'] - Contenido: passphrase
        try:
            passdb.setPassword(resp['result'], passphrase)
            status = 200
        except passdbException as error:
            message = "create_account(): Error creating file: %s" % error.value
            resp = {'status': 'error', 'message': message}
            status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve el numero del ultimo bloque
@ethgw.route('/block/last/', methods=["GET"])
@ethgw.route('/block/last', methods=["GET"])
def get_last_block():
    try:
        resp   = eth.eth_blockNumber()
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve el precio del gas de la red
@ethgw.route('/gas/price/', methods=["GET"])
@ethgw.route('/gas/price', methods=["GET"])
def get_gas_price():
    try:
        resp   = eth.eth_gasPrice()
        status = 200
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503
    return Response(response=dumps(resp), status=status)


# Devuelve el gas estimado a utilizar en la transaccion
@ethgw.route('/tx/estimategas/', methods=["POST"])
@ethgw.route('/tx/estimategas', methods=["POST"])
def get_tx_estimate():
    # Parametros madatorios
    mdt_params = ['destination']
    # Parametros opcionales
    opt_params = ['source', 'weis']

    # # Cargo el contenido del POST
    try:
        content = loads(request.data)
    except ValueError as e:
        resp   = {'status':'error', 'message':str(e)}
        return Response(response=dumps(resp), status=400)

    # Verifico parametros mandatorios
    for param in mdt_params:
        if not param in content:
            msg    = "%s key not found" % param 
            resp   = {'status':'error', 'message':' msg'}
            return Response(response=dumps(resp), status=400)

    # Cargo en None los paramtros opcionales si no fueron definidos
    for param in opt_params:
        if param not in content:
            content[param] = None

    try:
        resp   = eth.eth_estimateGas(content['destination'], content['source'], content['weis'])
        status = 201
    except socket.error as error:
        msg    = "ethrpc(): %s" % str(error)
        resp   = {'status':'error', 'message':msg}
        status = 503

    return Response(response=dumps(resp), status=status)


@ethgw.route('/test/<string:address>', methods=["GET"])
def test(address):
    #resp = discount_fee('0x1586da20defcc011356aa934cf35c1031fa90871', '0xf4E1D94C990F470E231Aa38bcc0178C1Ca9A02Ec', 20000000000000000)
    eth = ethrpc()
    resp = eth.personal_lockAccount(address)
    status = 200
    return Response(response=dumps(resp), status=status)



if __name__ == '__main__':
    handler = RotatingFileHandler('log/tx.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    ethgw.logger.addHandler(handler)
    ethgw.run(debug=True, host='0.0.0.0', port=6969)
