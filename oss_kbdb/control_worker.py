"""Worker de jobs do control plane; rode uma ou mais réplicas sem duplicar claims."""
from __future__ import annotations
import hashlib,hmac,json,os,time
from urllib import request
from cryptography.fernet import Fernet
from oss_kbdb.adapters.embeddings import LocalEmbedder,OpenAICompatibleEmbedder
from oss_kbdb.adapters.postgres import PostgresRepository
from oss_kbdb.adapters.s3 import S3ObjectStore
from oss_kbdb.services.enrichment import DeterministicEnricher,OpenAICompatibleEnricher
from oss_kbdb.services.ingestion import IngestionService
from oss_kbdb.config import Settings
from oss_kbdb.kb_defaults import database_url
def _decrypt(v):return json.loads(Fernet(os.environ['CONTROL_PLANE_FERNET_KEY'].encode()).decrypt(v).decode())
def _hook(url,secret,event):
 body=json.dumps(event,separators=(',',':')).encode();headers={'Content-Type':'application/json'}
 if secret: headers['X-OSS-KBDB-Signature']='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
 request.urlopen(request.Request(url,data=body,headers=headers,method='POST'),timeout=15).read()
def run_once():
 control=PostgresRepository(Settings.from_env().database_url)
 try:
  with control._conn.transaction(),control._conn.cursor() as c:
   c.execute("SELECT id,tenant_id,kb_id,payload FROM jobs WHERE status='queued' AND kind='ingest' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
   job=c.fetchone()
   if not job:return False
   c.execute("UPDATE jobs SET status='running' WHERE id=%s",(job[0],))
  kb=control._conn.execute('SELECT database_config_ciphertext,s3_config_ciphertext,embedding_config_ciphertext,enrichment_config_ciphertext,chunk_config,webhook_url,webhook_secret_ciphertext FROM knowledge_bases WHERE id=%s',(job[2],)).fetchone()
  dbcfg,s3cfg,embcfg,llmcfg=_decrypt(kb[0]),_decrypt(kb[1]),_decrypt(kb[2]),_decrypt(kb[3])
  chunks,hook=kb[4],kb[5]
  hooksecret=Fernet(os.environ['CONTROL_PLANE_FERNET_KEY'].encode()).decrypt(kb[6]).decode() if kb[6] else None
  data_db=PostgresRepository(database_url(dbcfg),schema_name=dbcfg['schema_name'])
  try:
   store=S3ObjectStore(endpoint_url=s3cfg.get('url'),region=s3cfg.get('region','us-east-1'),access_key_id=s3cfg.get('credentials',{}).get('access_key_id'),secret_access_key=s3cfg.get('credentials',{}).get('secret_access_key'))
   emb=LocalEmbedder(embcfg['model'],embcfg.get('dimensions',384)) if embcfg.get('provider','local')=='local' else OpenAICompatibleEmbedder(embcfg['url'],embcfg.get('credentials',{}).get('api_key'),embcfg['model'],embcfg['dimensions']);emb.model=embcfg['model']
   enr=DeterministicEnricher() if llmcfg.get('provider','deterministic')=='deterministic' else OpenAICompatibleEnricher(llmcfg['url'],llmcfg.get('credentials',{}).get('api_key'),llmcfg['model'])
   bucket,key=store.parse_uri(job[3]['source_uri']);out=IngestionService(data_db,emb,enr,max_tokens=chunks['max_tokens'],overlap_tokens=chunks['overlap_tokens'],min_tokens=chunks['min_tokens']).ingest(store.get(bucket,key),document_type=job[3]['document_type'])
   control._conn.execute("UPDATE jobs SET status='succeeded',finished_at=now() WHERE id=%s",(job[0],));control._conn.commit()
  finally:data_db.close()
  return True
 except Exception as exc:
  control._conn.execute("UPDATE jobs SET status='rejected',error=%s,finished_at=now() WHERE id=%s",(str(exc)[:1000],job[0]));control._conn.commit()
  if kb[5]: _hook(kb[5],hooksecret,{'event':'ingestion.rejected','job_id':str(job[0]),'kb_id':str(job[2]),'error':str(exc)[:1000]})
  return True
 finally:control.close()
