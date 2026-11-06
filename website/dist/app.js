(async function(){
let authState=await fetch('/api/auth').then(r=>{if(!r.ok)throw Error();return r.json();}).catch(()=>({configured:false,user:null}));
function reportEvent(code,extra={}){
  if(!authState.csrf)return;
  fetch('/api/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code,csrf:authState.csrf,...extra})}).catch(()=>{});
}
let visitorId;
try{visitorId=localStorage.getItem('d1ha_browser_visitor_v1');if(!/^[a-f0-9-]{36}$/.test(visitorId||'')){visitorId=crypto.randomUUID();localStorage.setItem('d1ha_browser_visitor_v1',visitorId);}}catch{visitorId=crypto.randomUUID();}
reportEvent('visit',{visitor_id:visitorId});
window.addEventListener('error',()=>reportEvent('javascript_error'));
window.addEventListener('unhandledrejection',()=>reportEvent('unhandled_promise'));
const accountPrefix=authState.user?'google_'+authState.user.account_key+'_':'';
const storageKey=key=>key.startsWith('d1ha_')?key.replace('d1ha_','d1ha_'+accountPrefix):key;
const $=s=>document.querySelector(s);
const form=$('#chat-form'),promptBox=$('#prompt'),messages=$('#messages'),welcome=$('#welcome');
const send=$('#send'),newChat=$('#new-chat'),mobileNew=$('#new-chat-mobile'),model=$('#model'),connection=$('#connection');
const historyList=$('#chat-history'),searchBox=$('#chat-search'),profileMenu=$('#profile-menu');
let busy=false,mode='deep',current=null;
const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(storageKey(key)))??fallback;}catch{return fallback;}};
function write(key,value){try{localStorage.setItem(storageKey(key),JSON.stringify(value));}catch{connection.textContent='Browser storage is full or unavailable. This session still works, but changes may not be saved.';}}
const savedUsage=read('d1ha_token_usage_v1',{});
const safeCount=value=>Number.isSafeInteger(value)&&value>=0?value:0;
const tokenUsage={input:safeCount(savedUsage.input),output:safeCount(savedUsage.output),last:safeCount(savedUsage.last)};
function renderTokenUsage(){
  $('#tokens-total').textContent=(tokenUsage.input+tokenUsage.output).toLocaleString();
  $('#tokens-input').textContent=tokenUsage.input.toLocaleString();
  $('#tokens-output').textContent=tokenUsage.output.toLocaleString();
  $('#tokens-last').textContent=tokenUsage.last.toLocaleString();
}
function trackUsage(usage){
  const input=safeCount(usage?.prompt_tokens),output=safeCount(usage?.generated_tokens);
  tokenUsage.input+=input;tokenUsage.output+=output;tokenUsage.last=input+output;
  write('d1ha_token_usage_v1',tokenUsage);renderTokenUsage();
}
$('#tokens-button').addEventListener('click',()=>{closeProfileMenu();renderTokenUsage();$('#tokens-dialog').showModal();});
$('#close-tokens').addEventListener('click',()=>$('#tokens-dialog').close());
const rawProfile=read('d1ha_profile_v1',{});
let profile={name:typeof rawProfile.name==='string'?rawProfile.name.slice(0,24):(authState.user?.name||'You').slice(0,24),colour:['violet','pink','blue'].includes(rawProfile.colour)?rawProfile.colour:'violet',theme:rawProfile.theme==='light'?'light':'dark',model:['d1ha','d1ha-1','d1ha-1-1','d1ha-1-2','d1ha-1-3','d1ha-1-4','d1ha-1-5','classic'].includes(rawProfile.model)?rawProfile.model:'d1ha',mode:rawProfile.mode==='light'?'light':'deep'};
let stored=read('d1ha_chats_v1',[]);
let chats=Array.isArray(stored)?stored.filter(c=>c&&/^[a-f0-9-]{36}$/.test(c.id)&&Array.isArray(c.messages)).slice(0,25).map(c=>({id:c.id,title:String(c.title||'New chat').slice(0,60),messages:c.messages.filter(m=>m&&['user','assistant'].includes(m.role)&&typeof m.text==='string').slice(-40)})):[];
function saveChats(){chats=chats.slice(0,25);write('d1ha_chats_v1',chats);write('d1ha_active_chat',current?.id);renderHistory();}
function createChat(){chats=chats.filter(c=>c.messages.length);current={id:crypto.randomUUID(),title:'New chat',messages:[]};chats.unshift(current);saveChats();renderConversation();closeSidebar();promptBox.focus();}
function renderHistory(){
  historyList.replaceChildren();const query=searchBox.value.toLowerCase();
  const visible=chats.filter(c=>c.messages.length&&(c.title.toLowerCase().includes(query)||c.messages.some(m=>m.text.toLowerCase().includes(query))));
  for(const chat of visible){const button=document.createElement('button');button.className='chat-item'+(chat.id===current?.id?' active':'');button.textContent=chat.title;button.title=chat.title;button.disabled=busy;button.addEventListener('click',()=>{if(busy)return;current=chat;write('d1ha_active_chat',chat.id);renderConversation();renderHistory();closeSidebar();});historyList.append(button);}
  if(!visible.length){const note=document.createElement('p');note.className='history-empty';note.textContent=query?'No matching chats.':'Your conversations will appear here.';historyList.append(note);}
}
function fillInline(element,text){
  element.replaceChildren();const pattern=/https?:\/\/[^\s<>]+/g;let cursor=0;
  for(const hit of text.matchAll(pattern)){element.append(document.createTextNode(text.slice(cursor,hit.index)));const link=document.createElement('a');link.href=hit[0];link.textContent=hit[0];link.target='_blank';link.rel='noopener noreferrer';element.append(link);cursor=hit.index+hit[0].length;}
  element.append(document.createTextNode(text.slice(cursor)));
}
function fill(element,text){
  element.replaceChildren();const blocks=text.split(/```([^\n`]*)\n([\s\S]*?)```/g);
  // Parse only fenced code; text and links always use DOM text nodes.
  for(let i=0;i<blocks.length;i+=3){
    if(blocks[i]){const prose=document.createElement('span');fillInline(prose,blocks[i]);element.append(prose);}
    if(i+2<blocks.length){
      const panel=document.createElement('div');panel.className='code-panel';
      const bar=document.createElement('div');bar.className='code-heading';
      const language=document.createElement('span');language.textContent=blocks[i+1].trim()||'Code';bar.append(language);
      const copy=document.createElement('button');copy.type='button';copy.textContent='Copy code';
      copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(blocks[i+2]);copy.textContent='Copied';setTimeout(()=>copy.textContent='Copy code',1500);}catch{connection.textContent='Select the code to copy it.';}});bar.append(copy);
      const pre=document.createElement('pre'),code=document.createElement('code');code.textContent=blocks[i+2];pre.append(code);panel.append(bar,pre);element.append(panel);
    }
  }
}
function message(role,text,pending=false,retryPrompt=null){
  const row=document.createElement('div');row.className=`message ${role}`;
  if(role!=='user'){const avatar=document.createElement('span');avatar.className='avatar';avatar.textContent='✳';avatar.setAttribute('aria-hidden','true');row.append(avatar);}
  const body=document.createElement('div');body.className='message-text'+(pending?' pending':'');row.append(body);messages.append(row);fill(body,text);
  if(role==='assistant'&&!pending)addActions(body,text,retryPrompt);return {row,body};
}
function addActions(body,text,retryPrompt){
  const actions=document.createElement('div');actions.className='answer-actions';
  const copy=document.createElement('button');copy.type='button';copy.className='copy-reply';copy.textContent='Copy';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(text);copy.textContent='Copied';setTimeout(()=>copy.textContent='Copy',1500);}catch{connection.textContent='Select the answer text to copy it.';}});actions.append(copy);
  if(retryPrompt){const again=document.createElement('button');again.type='button';again.className='again';again.dataset.again='true';again.textContent='↻ Another reply';again.addEventListener('click',()=>ask(retryPrompt,false));actions.append(again);}body.append(actions);
}
function renderConversation(){$('#chat-tools').disabled=busy||!current?.messages.length;messages.replaceChildren();welcome.classList.toggle('hidden',Boolean(current?.messages.length));for(const m of current?.messages||[])message(m.role,m.text,false,m.prompt||null);}
function scrollDown(){window.scrollTo({top:document.body.scrollHeight,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
function setBusy(value){busy=value;send.disabled=value;newChat.disabled=value;mobileNew.disabled=value;model.disabled=value;$('#chat-tools').disabled=value||!current?.messages.length;document.querySelectorAll('[data-mode],[data-again],.chat-item').forEach(b=>b.disabled=value);promptBox.setAttribute('aria-busy',String(value));}
async function request(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,account_key:authState.user?.account_key||null})});const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed.');return data;}
async function ask(text,showUser=true){
  if(!text||busy)return;if(!current)createChat();
  welcome.classList.add('hidden');connection.textContent='';
  if(showUser){current.messages.push({role:'user',text});message('user',text);if(current.title==='New chat')current.title=text.replace(/\s+/g,' ').slice(0,45);}
  promptBox.value='';promptBox.style.height='auto';updateCharacterCount();saveChats();
  const output=message('assistant','Preparing your reply',true);setBusy(true);scrollDown();
  const words=['Preparing your reply','Working','Still working'];let index=0;const timer=setInterval(()=>output.body.textContent=words[++index%words.length],3500);
  try{
    const [data]=await Promise.all([request('/api/chat',{message:text,model:model.value,mode,chat_id:current.id}),new Promise(resolve=>setTimeout(resolve,750))]);
    trackUsage(data.usage);clearInterval(timer);output.body.classList.remove('pending');fill(output.body,data.reply);addActions(output.body,data.reply,text);
    current.messages.push({role:'assistant',text:data.reply,prompt:text});current.messages=current.messages.slice(-40);saveChats();
  }catch(error){reportEvent('chat_request_failed');clearInterval(timer);output.body.classList.remove('pending');output.row.classList.add('error');fill(output.body,error.message==='Failed to fetch'?'Cannot reach D1ha. Check that web.py is still running.':error.message);}
  finally{setBusy(false);promptBox.focus();scrollDown();}
}
form.addEventListener('submit',event=>{event.preventDefault();ask(promptBox.value.trim());});
promptBox.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();form.requestSubmit();}});
function updateCharacterCount(){$('#character-count').textContent=promptBox.value.length.toLocaleString()+' / 1,000';}
promptBox.addEventListener('input',()=>{updateCharacterCount();promptBox.style.height='auto';promptBox.style.height=Math.min(promptBox.scrollHeight,120)+'px';});
document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.prompt)));
function selectMode(value){mode=value;document.querySelectorAll('[data-mode]').forEach(b=>{const active=b.dataset.mode===mode;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});profile.mode=mode;write('d1ha_profile_v1',profile);}
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>selectMode(b.dataset.mode)));
model.value=profile.model;model.addEventListener('change',()=>{profile.model=model.value;write('d1ha_profile_v1',profile);});
newChat.addEventListener('click',()=>{if(!busy)createChat();});mobileNew.addEventListener('click',()=>{if(!busy)createChat();});searchBox.addEventListener('input',renderHistory);
function syncSidebar(){$('#sidebar').inert=matchMedia('(max-width:680px)').matches&&!$('#sidebar').classList.contains('open');}
function closeSidebar(){$('#sidebar').classList.remove('open');$('#sidebar-overlay').classList.add('hidden');$('#menu-toggle').setAttribute('aria-expanded','false');syncSidebar();}
$('#menu-toggle').addEventListener('click',()=>{const open=$('#sidebar').classList.toggle('open');$('#sidebar-overlay').classList.toggle('hidden',!open);$('#menu-toggle').setAttribute('aria-expanded',String(open));syncSidebar();});$('#sidebar-overlay').addEventListener('click',closeSidebar);
function closeProfileMenu(){profileMenu.classList.add('hidden');$('#profile-toggle').setAttribute('aria-expanded','false');}
$('#profile-toggle').addEventListener('click',()=>{const open=profileMenu.classList.contains('hidden');profileMenu.classList.toggle('hidden',!open);$('#profile-toggle').setAttribute('aria-expanded',String(open));});
document.addEventListener('click',event=>{if(!event.target.closest('.profile-area'))closeProfileMenu();});document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeProfileMenu();closeSidebar();}});
function renderProfile(){
  const name=profile.name.trim()||'You';document.querySelector('.profile-label>span').textContent=authState.user?'Google verified':'Local profile';$('#profile-name').textContent=name;$('#profile-avatar').textContent=Array.from(name)[0].toUpperCase();$('#profile-avatar').dataset.color=profile.colour;
  document.body.classList.toggle('light',profile.theme==='light');$('#theme-toggle').textContent=profile.theme==='light'?'Switch to dark theme ◐':'Switch to light theme ◐';
  $('#welcome-greeting').textContent=name==='You'?'YOUR OWN LITTLE AI SPACE':`WELCOME BACK, ${name.toUpperCase()}`;
}
$('#edit-profile').addEventListener('click',()=>{$('#display-name').value=profile.name==='You'?'':profile.name;document.querySelector(`input[name="avatar-colour"][value="${profile.colour}"]`).checked=true;closeProfileMenu();$('#profile-dialog').showModal();$('#display-name').focus();});
$('#close-profile').addEventListener('click',()=>$('#profile-dialog').close());
$('#profile-form').addEventListener('submit',event=>{event.preventDefault();profile.name=$('#display-name').value.trim().slice(0,24)||'You';profile.colour=document.querySelector('input[name="avatar-colour"]:checked').value;write('d1ha_profile_v1',profile);renderProfile();$('#profile-dialog').close();});
$('#theme-toggle').addEventListener('click',()=>{profile.theme=profile.theme==='dark'?'light':'dark';write('d1ha_profile_v1',profile);renderProfile();closeProfileMenu();});
$('#about-button').addEventListener('click',()=>{closeProfileMenu();$('#about-dialog').showModal();});$('#close-about').addEventListener('click',()=>$('#about-dialog').close());
$('#welcome-tokens').addEventListener('click',()=>{$('#tokens-button').click();});
$('#chat-tools').addEventListener('click',()=>{
  if(busy||!current?.messages.length)return;
  $('#chat-name').value=current.title;$('#delete-confirmation').classList.add('hidden');$('#delete-chat').classList.remove('hidden');$('#chat-options-status').textContent='';
  $('#chat-options-dialog').showModal();$('#chat-name').focus();
});
$('#close-chat-options').addEventListener('click',()=>$('#chat-options-dialog').close());
$('#rename-form').addEventListener('submit',event=>{
  event.preventDefault();if(busy||!current)return;
  current.title=$('#chat-name').value.trim().slice(0,60)||'Untitled chat';saveChats();$('#chat-options-dialog').close();
});
$('#export-chat').addEventListener('click',()=>{
  if(!current)return;
  const text=current.title+'\n\n'+current.messages.map(m=>(m.role==='user'?'You':'D1ha')+':\n'+m.text).join('\n\n');
  const blob=new Blob([text],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download=(current.title.replace(/[^a-z0-9а-яё _-]/gi,'').slice(0,45)||'D1ha-chat')+'.txt';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('#chat-options-status').textContent='Export prepared. Check your downloads.';
});
$('#delete-chat').addEventListener('click',()=>{$('#delete-chat').classList.add('hidden');$('#delete-confirmation').classList.remove('hidden');$('#cancel-delete').focus();});
$('#cancel-delete').addEventListener('click',()=>{$('#delete-confirmation').classList.add('hidden');$('#delete-chat').classList.remove('hidden');});
$('#confirm-delete').addEventListener('click',async()=>{
  if(busy||!current)return;const id=current.id;
  $('#confirm-delete').disabled=true;
  try{await request('/api/reset',{chat_id:id});chats=chats.filter(c=>c.id!==id);current=null;$('#chat-options-dialog').close();createChat();}
  catch(error){$('#chat-options-status').textContent=error.message;}
  finally{$('#confirm-delete').disabled=false;}
});
$('#feedback-button').addEventListener('click',()=>{closeProfileMenu();$('#feedback-dialog').showModal();$('#feedback-message').focus();});
$('#close-feedback').addEventListener('click',()=>$('#feedback-dialog').close());
$('#feedback-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('#feedback-submit'),status=$('#feedback-status');
  button.disabled=true;status.textContent='Saving feedback…';
  try{
    const data=await request('/api/feedback',{message:$('#feedback-message').value.trim(),rating:Number($('#feedback-rating').value),category:$('#feedback-category').value,model:model.value,csrf:authState.csrf});
    $('#feedback-form').reset();status.textContent=`Thank you! Feedback #${data.id} saved on the server.`;
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
});
renderProfile();selectMode(profile.mode);window.addEventListener('resize',syncSidebar);syncSidebar();
current=chats.find(c=>c.id===read('d1ha_active_chat',null))||chats[0]||null;if(!current)createChat();else{renderConversation();renderHistory();}
fetch('/api/info').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{document.querySelector('.version').textContent=data.version;}).catch(()=>{connection.textContent='D1ha is offline. Please try again later.';send.disabled=true;});

let googleInitialized=false;
const accountButton=$('#google-account');
accountButton.textContent=authState.user?'Google account':'Sign in with Google';
async function openGoogle(){
  closeProfileMenu();$('#auth-dialog').showModal();
  if(authState.user){
    $('#auth-title').textContent='Your Google account';
    $('#auth-description').textContent=`Signed in as ${authState.user.name} (${authState.user.email}). Chat history stays in this browser and is not synced to Google.`;
    $('#google-signout').classList.remove('hidden');$('#continue-guest').classList.add('hidden');return;
  }
  if(!authState.configured){
    $('#auth-status').textContent='Google sign-in has not been set up by the site owner. You can keep using the local profile meanwhile.';
    return;
  }
  if(googleInitialized)return;
  $('#auth-status').textContent='Loading Google’s secure sign-in button…';
  try{
    await new Promise((resolve,reject)=>{
      if(window.google?.accounts?.id){resolve();return;}
      const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true;script.onload=resolve;script.onerror=()=>reject(Error('Could not load Google sign-in. Check your connection.'));document.head.append(script);
    });
    window.google.accounts.id.initialize({client_id:authState.client_id,nonce:authState.nonce,auto_select:false,ux_mode:'popup',callback:async response=>{
      $('#auth-status').textContent='Verifying your Google sign-in…';
      try{await request('/api/auth/google',{credential:response.credential,csrf:authState.csrf});window.location.reload();}
      catch(error){$('#auth-status').textContent=error.message;}
    }});
    window.google.accounts.id.renderButton($('#google-button'),{type:'standard',theme:'outline',size:'large',shape:'pill',text:'signin_with'});
    googleInitialized=true;$('#auth-status').textContent='Choose your account in Google’s sign-in window. D1ha never asks for your Google password.';
  }catch(error){$('#auth-status').textContent=error.message;}
}
accountButton.addEventListener('click',openGoogle);
$('#close-auth').addEventListener('click',()=>$('#auth-dialog').close());
$('#continue-guest').addEventListener('click',()=>$('#auth-dialog').close());
$('#google-signout').addEventListener('click',async()=>{
  try{await request('/api/auth/logout',{csrf:authState.csrf});window.google?.accounts?.id?.disableAutoSelect?.();window.location.reload();}
  catch(error){$('#auth-status').textContent=error.message;}
});
})();
