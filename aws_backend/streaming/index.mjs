import {DynamoDBClient,GetItemCommand,DeleteItemCommand} from '@aws-sdk/client-dynamodb';
import {S3Client,GetObjectCommand} from '@aws-sdk/client-s3';
import {streamEvents} from './stream.mjs';
import {TranscribeStreamingClient,StartStreamTranscriptionCommand} from '@aws-sdk/client-transcribe-streaming';
import {speechEvents} from './speech.mjs';

const region=process.env.AWS_REGION || 'us-east-1';
const dynamo=new DynamoDBClient({region,maxAttempts:1,requestHandler:{requestTimeout:5000,connectionTimeout:3000}});
const s3=new S3Client({region,maxAttempts:1});
const speech=new TranscribeStreamingClient({region,maxAttempts:1});
const TableName=process.env.VDS_STATE_TABLE;
const get=async (owner,key)=>{
  const {Item}=await dynamo.send(new GetItemCommand({TableName,Key:{pk:{S:owner},sk:{S:key}},ConsistentRead:true}));
  return Item?.doc?.S ? JSON.parse(Item.doc.S) : null;
};
const store={
  async consume(hash,now){
    try{
      const {Attributes:a}=await dynamo.send(new DeleteItemCommand({TableName,Key:{pk:{S:'streamticket#'+hash},sk:{S:'ticket'}},
        ConditionExpression:'attribute_exists(pk) AND expires_at >= :now',ExpressionAttributeValues:{':now':{N:String(now)}},ReturnValues:'ALL_OLD'}));
      return a ? {owner:a.owner.S,run_id:a.run_id?.S,dataset_id:a.dataset_id?.S,kind:a.kind?.S || 'analysis',expires_at:Number(a.expires_at.N)} : null;
    }catch(error){if(error.name==='ConditionalCheckFailedException')return null;throw error;}
  },
  dataset:(owner,id)=>get(owner,'dataset#'+id),
  run:(owner,id)=>get(owner,'run#'+id),
  async result(owner,key){
    if(!/^[a-f0-9]{32}\/runs\/[a-f0-9]{32}\.json$/.test(key))throw new Error('invalid_artifact');
    const {Body,ContentLength}=await s3.send(new GetObjectCommand({Bucket:process.env.VDS_DATA_BUCKET,Key:owner+'/'+key}));
    if(ContentLength>2*1024*1024){Body.destroy();throw new Error('output_limit');}
    return JSON.parse(await Body.transformToString());
  }
};

export const handler=awslambda.streamifyResponse(async (event,responseStream)=>{
  const out=awslambda.HttpResponseStream.from(responseStream,{statusCode:200,headers:{'Content-Type':'text/event-stream','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
  try{
    if(event.rawPath==='/api/v2/speech/transcribe'){
      if((event.body || '').length>1200000)throw new Error('invalid_request');
      await speechEvents(event,out,store,async function*(AudioStream,signal){
        const response=await speech.send(new StartStreamTranscriptionCommand({LanguageCode:'en-US',MediaEncoding:'pcm',MediaSampleRateHertz:16000,
          EnablePartialResultsStabilization:true,PartialResultsStability:'high',AudioStream}),{abortSignal:signal});
        for await(const item of response.TranscriptResultStream)yield item;
      });
    }else{
      if((event.body || '').length>2048)throw new Error('invalid_request');
      await streamEvents(event,out,store);
    }
  }catch{
    // No request, ticket, source text or exception payload is logged.
    if(!out.destroyed){out.write('event: unavailable\ndata: {"code":"stream_unavailable"}\n\n');out.end();}
  }
});
