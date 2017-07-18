from json import loads
from json import dumps

import httplib2


'''
    Convert to decimal the values from the dictionary given as parameters
'''
def decimal_converter(d, values=[]):
    for v in values:
        if v in d:
            d[v] = int(d[v], 16)
    return d



class ethrpc(object):
    def __init__(self, hostname='127.0.0.1',port='8545',ver='2.0'):
        self.http = httplib2.Http()
        self.hostname  = hostname
        self.port      = port
        self.header    = {'Content-Type': 'text/plain'}
        self.version   = ver


    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # Support Functions to JSON RPC PROTOCOL
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
    def get_url(self):
        return 'http://%s:%s' % (self.hostname,self.port)


    def doPost(self, url, body):
        return self.http.request(url,method='POST',headers=self.header,body=dumps(body))


    def jsonrpc(self, method, params=[], id=1):
        body = {}

        if self.version == '1.0':
            pass
        elif self.version == '1.1':
            pass
        elif self.version == '2.0':
            body['jsonrpc'] = self.version
            body['method']  = method
            body['params']  = params
            body['id']      = id


        if body is not {}:
            response, content = self.doPost(self.get_url(),body)
            if response['status'] == '200':
                resp = loads(content)
                if 'error' in resp:
                    message = resp['error']['message']
                    ret = {'status': 'error', 'message': message}
                    return ret
                else:
                    result = resp['result']
                    ret = {'status': 'success', 'result': result}
                    return ret
        else:
            ret = {'status': 'error', 'message': "response is not 200"}
            return ret


    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # Ethereum CLI Interface
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    def eth_getBalance(self, address, state='latest'):
        '''
            The eth_getBalance RPC returns the balance of given address.
        '''
        params = [address, state]
        rpc_ret = self.jsonrpc('eth_getBalance', params, 1)
        if rpc_ret['status'] == 'success':
            rpc_ret = decimal_converter(rpc_ret, ['result'])
        return rpc_ret


    def personal_sendTransaction(self, src, dst, weis, passphrase):
        '''
            Validate the given passphrase and submit transaction.
        '''
        weis_hex = hex(weis)
        tx = {'from': src, 'to': dst, 'value': weis_hex}
        params = [tx, passphrase]
        return self.jsonrpc('personal_sendTransaction', params, 1)


    def personal_listAccounts(self):
        '''
            Returns all the Ethereum account addresses of all keys in the key store.
        '''
        return self.jsonrpc('personal_listAccounts')


    def personal_newAccount(self, passphrase):
        '''
            Generates a new private key and stores it in the key store directory. The key file is encrypted with the given passphrase. Returns the address of the new account.
        '''
        params  = [passphrase]
        return self.jsonrpc('personal_newAccount', params)


    def eth_getTransactionByHash(self, tx_hash):
        '''
            Returns the information about a transaction requested by transaction hash.
        '''
        rpc_ret = self.jsonrpc('eth_getTransactionByHash', [tx_hash])
        if rpc_ret['status'] == 'success':
            values = ['nonce', 'v', 'gas', 'value', 'blockNumber', 'gasPrice', 'transactionIndex']
            rpc_ret['result'] = decimal_converter(rpc_ret['result'], values)
        return rpc_ret


    def eth_getTransactionReceipt(self, tx_hash):
        '''
            Returns the receipt of a transaction by transaction hash.
        '''
        rpc_ret = self.jsonrpc('eth_getTransactionReceipt', [tx_hash])
        if rpc_ret['status'] == 'success':
            values = ['transactionIndex', 'blockNumber', 'cumulativeGasUsed', 'gasUsed']
            rpc_ret['result'] = decimal_converter(rpc_ret['result'], values)
        return rpc_ret


    def eth_blockNumber(self):
        '''
            Returns the number of most recent block.
        '''
        rpc_ret = self.jsonrpc('eth_blockNumber', [], 83)
        rpc_ret = decimal_converter(rpc_ret, ['result'])
        return rpc_ret



