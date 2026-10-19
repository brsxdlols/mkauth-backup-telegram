<?php
// Root-only backend. Never return Telegram responses, URLs or credentials.
if (PHP_SAPI !== 'cli' || posix_geteuid() !== 0) exit(1);
const STATE = '/var/lib/mka-backup-telegram';
function readj($name, $default=[]) { $v=json_decode(@file_get_contents(STATE.'/'.$name),true); return is_array($v)?$v:$default; }
function writej($name,$v) { $p=STATE.'/'.$name; $t=$p.'.tmp'; if(file_put_contents($t,json_encode($v,JSON_UNESCAPED_UNICODE),LOCK_EX)===false) throw new Exception('Falha ao salvar configuração.'); chmod($t,0600); rename($t,$p); }
function latest() { $files=[]; foreach(glob('/opt/mk-auth/bckp/*') as $p) if(is_file($p)&&!is_link($p)) $files[]=$p; usort($files,function($a,$b){return filemtime($b)<=>filemtime($a);}); return $files?$files[0]:null; }
function api($c,$method,$data=[]) {
 $h=curl_init('https://api.telegram.org/bot'.$c['token'].'/'.$method);
 curl_setopt_array($h,[CURLOPT_NOPROGRESS=>false,CURLOPT_PROGRESSFUNCTION=>function($h,$dt,$dn,$ut,$un)use($method){static $last=0;if($method==='sendDocument'&&microtime(true)-$last>0.8){$last=microtime(true);writej('progress.json',['percent'=>$ut>0?min(99,(int)floor($un/$ut*100)):0,'phase'=>$ut>0&&$un>=$ut?'Aguardando confirmação…':'Enviando arquivo…','updated'=>time()]);}return 0;},CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>$data,CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>15,CURLOPT_TIMEOUT=>$method==='sendDocument'?600:30]);
 $raw=curl_exec($h);$code=curl_getinfo($h,CURLINFO_HTTP_CODE);curl_close($h);$r=is_string($raw)?json_decode($raw,true):null;
 if(!is_array($r)||empty($r['ok'])) { $msg=$code===401?'Token inválido.':($code===403?'O bot não tem permissão neste chat.':($code===413?'Backup acima do limite de envio.':($code===429?'Telegram limitou os envios. Aguarde e tente novamente.':'Falha na comunicação com o Telegram. Confira token, Chat ID e acesso do bot.'))); throw new Exception($msg); } return $r['result'];
}
$a=isset($argv[1])&&$argv[1]==='tick'?['action'=>'tick']:json_decode(stream_get_contents(STDIN,8193),true);
$c=readj('config.json');$action=is_array($a)?($a['action']??''):'';
try {
 if($action==='status') { $p=latest(); echo json_encode(['ok'=>true,'config'=>['chat'=>$c['chat']??'','name'=>$c['name']??'','time'=>$c['time']??'06:30','enabled'=>!empty($c['enabled']),'token_set'=>!empty($c['token']),'token'=>$c['token']??''],'latest'=>$p?['name'=>basename($p),'size'=>filesize($p),'date'=>date('d/m/Y H:i',filemtime($p))]:null,'progress'=>readj('progress.json'),'history'=>readj('history.json'),'timezone'=>date_default_timezone_get()]);exit; }
 if($action==='discover'){
 $token=trim((string)($a['token']??''));if($token==='')$token=$c['token']??'';
 if(!preg_match('/^\d{5,20}:[A-Za-z0-9_-]{20,150}$/D',$token))throw new Exception('Informe o token do bot antes de buscar chats.');
 $candidate=['token'=>$token];$bot=api($candidate,'getMe');$webhook=api($candidate,'getWebhookInfo');
 if(!empty($webhook['url']))throw new Exception('Este bot usa webhook em outra integração. A busca automática não está disponível; informe o Chat ID manualmente ou use um bot exclusivo para backups.');
 $updates=api($candidate,'getUpdates',['limit'=>100,'timeout'=>0]);$chats=[];
 foreach($updates as $update){foreach(['message','edited_message','channel_post'] as $kind){$m=$update[$kind]??null;if(!is_array($m)||empty($m['chat']['id']))continue;$chat=$m['chat'];$id=(string)$chat['id'];$chats[$id]=['id'=>$id,'title'=>$chat['title']??trim(($chat['first_name']??'').' '.($chat['last_name']??'')),'type'=>$chat['type']??'chat'];}}
 echo json_encode(['ok'=>true,'message'=>$chats?'Selecione o chat de destino e depois salve a configuração.':'Nenhum chat encontrado. Adicione o bot ao grupo, envie /start@'.($bot['username']??'seu_bot').' e clique em Buscar chats novamente.','chats'=>array_values($chats),'bot'=>$bot['username']??''],JSON_INVALID_UTF8_SUBSTITUTE);exit;
 }
 if($action==='download'){$p=latest();if(!$p)exit(1);readfile($p);exit;}
 $lock=fopen(STATE.'/lock','c');if(!flock($lock,LOCK_EX|LOCK_NB))throw new Exception('Já existe uma operação em andamento. Aguarde.');
 if($action==='toggle'){$c['enabled']=!empty($a['enabled']);writej('config.json',$c);echo json_encode(['ok'=>true,'message'=>$c['enabled']?'Envio automático ativado.':'Envio automático desativado.']);exit;}
 if($action==='inspect'){
 $p=latest();if(!$p)throw new Exception('Nenhum backup disponível.');if(time()-filemtime($p)<120)throw new Exception('Aguarde a geração do backup terminar.');if(file_get_contents($p,false,null,0,3)!=='BZh')throw new Exception('Formato não reconhecido para validação.');$before=stat($p);
 $job=proc_open(['/usr/bin/timeout','120','/bin/bzip2','-t',$p],[['file','/dev/null','r'],['file','/dev/null','w'],['file','/dev/null','w']],$pipes);if(!is_resource($job)||proc_close($job)!==0)throw new Exception('Teste falhou ou excedeu o tempo limite. O arquivo pode estar incompleto ou corrompido.');clearstatcache(true,$p);$after=stat($p);if($before['size']!==$after['size']||$before['mtime']!==$after['mtime'])throw new Exception('Arquivo alterado durante a verificação. Repita o teste.');$message='Compressão bzip2 íntegra, sem corrupção detectada: '.basename($p).'. SHA-256: '.hash_file('sha256',$p).'. Não substitui uma restauração de teste.';$history=readj('history.json');array_unshift($history,['date'=>date('d/m/Y H:i:s'),'action'=>'inspect','ok'=>true,'message'=>$message]);writej('history.json',array_slice($history,0,100));echo json_encode(['ok'=>true,'message'=>$message]);exit;
 }
 if($action==='save') {
  $token=trim((string)($a['token']??''));if($token==='')$token=$c['token']??'';
  $chat=trim((string)($a['chat']??''));$name=trim((string)($a['name']??''));$time=(string)($a['time']??'');
  if(!preg_match('/^\d{5,20}:[A-Za-z0-9_-]{20,150}$/D',$token))throw new Exception('Informe um token válido.');
  if(!preg_match('/^-?\d{1,25}$/D',$chat))throw new Exception('Informe um Chat ID numérico válido.');
  if($name===''||strlen($name)>120||preg_match('/[\x00-\x1f]/',$name))throw new Exception('Informe um nome com até 120 caracteres.');
  if(!preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/D',$time))throw new Exception('Horário inválido.');
  $c=['token'=>$token,'chat'=>$chat,'name'=>$name,'time'=>$time,'enabled'=>!empty($a['enabled'])];writej('config.json',$c);
  echo json_encode(['ok'=>true,'message'=>'Configuração salva.']);exit;
 }
 if(!in_array($action,['test','send','tick'],true))throw new Exception('Operação inválida.');
 if($action==='tick') { $run=readj('schedule.json');$today=date('Y-m-d');if(empty($c['enabled'])||date('H:i')<($c['time']??'06:30')||($run['date']??'')===$today)exit; writej('schedule.json',['date'=>$today]); }
 if(empty($c['token'])||empty($c['chat']))throw new Exception('Salve o token e o Chat ID primeiro.');
 if($action==='test') { $bot=api($c,'getMe'); api($c,'getChat',['chat_id'=>$c['chat']]);api($c,'sendMessage',['chat_id'=>$c['chat'],'text'=>'✅ Integração de backup MK-AUTH validada: '.$c['name']]);$message='Integração validada e mensagem recebida pelo chat. Bot: @'.($bot['username']??''); }
 else { writej('progress.json',['percent'=>0,'phase'=>'Preparando envio…','updated'=>time()]);$p=latest();if(!$p)throw new Exception('Nenhum backup encontrado em /opt/mk-auth/bckp.');if(time()-filemtime($p)<120)throw new Exception('O backup é muito recente e pode estar sendo gerado. Aguarde dois minutos.');if(filesize($p)>50*1024*1024)throw new Exception('O backup ultrapassa 50 MB, limite adotado para a API do Telegram.');if(filesize($p)===0)throw new Exception('O arquivo de backup está vazio.');$size=filesize($p);$mtime=filemtime($p);$caption='💾 MK-AUTH: '.$c['name']."\n📦 Backup: ".basename($p)."\n🕐 Gerado: ".date('d/m/Y H:i:s',$mtime)."\n📤 Enviado: ".date('d/m/Y H:i:s'); api($c,'sendDocument',['chat_id'=>$c['chat'],'document'=>new CURLFile($p),'caption'=>$caption]);$message='Backup '.basename($p).' enviado com sucesso.'; }
 $history=readj('history.json');array_unshift($history,['date'=>date('d/m/Y H:i:s'),'action'=>$action,'ok'=>true,'message'=>$message]);writej('history.json',array_slice($history,0,100));echo json_encode(['ok'=>true,'message'=>$message]);
} catch(Throwable $e) { $message=$e instanceof Exception?$e->getMessage():'Falha interna na operação.';if(!in_array($action,['status','save','discover'],true)){$h=readj('history.json');array_unshift($h,['date'=>date('d/m/Y H:i:s'),'action'=>$action,'ok'=>false,'message'=>$message]);writej('history.json',array_slice($h,0,100));} echo json_encode(['ok'=>false,'message'=>$message]);exit(1); }
