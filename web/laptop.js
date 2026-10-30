/* Local laptop controls. Server-owned proposals; file text is never HTML. */
(() => {
  'use strict';
  window.RaphaelLaptop = class {
    constructor({api,notify,onResult,onPending}) {
      this.api=api;this.notify=notify;this.onResult=onResult;this.onPending=onPending;
      this.$=id=>document.getElementById(id);this.signature='';this.loading=false;
      this.$('fileAccessForm').addEventListener('submit',event=>{
        event.preventDefault();this.requestAccess(event.submitter?.value||'browse_folder',this.$('fileAccessPath').value.trim());
      });
      this.$('laptopEnabled').addEventListener('change',async event=>{
        event.target.disabled=true;
        try { await api('/api/laptop/access',{enabled:event.target.checked});await this.refresh(); }
        catch(error){notify(error.message);event.target.checked=!event.target.checked;}
        finally {event.target.disabled=false;}
      });
      this.$('checkHardware').addEventListener('click',async event=>{
        event.target.disabled=true;this.$('hardwareResult').textContent='Reading this laptop…';
        try {
          const r=await api('/api/laptop/system');
          this.$('hardwareResult').textContent=[
            r.model&&'Laptop: '+[r.manufacturer,r.model].filter(Boolean).join(' '),
            r.cpu&&'Processor: '+r.cpu,
            r.ram_gb&&'Memory: '+r.ram_gb+' GB'+(r.ram_available_gb?' ('+r.ram_available_gb+' GB available)':''),
            r.graphics?.length&&'Graphics: '+r.graphics.join(', '),
            r.operating_system&&'System: '+r.operating_system,
            r.workspace_disk&&'Workspace drive: '+r.workspace_disk.free_gb+' GB free of '+r.workspace_disk.total_gb+' GB',
            r.graphics_status
          ].filter(Boolean).join('\n\n');
        }
        catch(error){this.$('hardwareResult').textContent=error.message;}
        finally {event.target.disabled=false;}
      });
    }
    status(status) {
      if(!status)return;
      this.$('laptopEnabled').checked=status.enabled;
      this.$('workspacePath').textContent=status.workspace;
      this.$('laptopStatus').textContent=status.enabled?'On · changes need approval':'Off';
      this.$('checkHardware').disabled=!status.enabled;
      if(!this.$('laptopApps').children.length)for(const app of status.apps){
        const button=document.createElement('button');button.className='secondary-button';button.textContent=app.name;
        button.addEventListener('click',async()=>{
          button.disabled=true;
          try{const result=await this.api('/api/laptop/open',{app:app.id});this.notify(result.message);}
          catch(error){this.notify(error.message);}
          finally{button.disabled=!this.$('laptopEnabled').checked;}
        });this.$('laptopApps').append(button);
      }
      this.$('laptopApps').querySelectorAll('button').forEach(button=>button.disabled=!status.enabled);
      if(!this.$('filePlaces').children.length)for(const place of status.places||[]){
        const button=document.createElement('button');button.className='secondary-button';button.textContent=place.name;
        button.addEventListener('click',()=>{this.$('fileAccessPath').value=place.path;this.requestAccess('browse_folder',place.path);});
        this.$('filePlaces').append(button);
      }
      this.$('fileAccess').querySelectorAll('input,button').forEach(el=>el.disabled=!status.enabled);
    }
    async requestAccess(action,path){
      try{await this.api('/api/laptop/files',{action,path});await this.receive();}
      catch(error){this.notify(error.message);}
    }
    async refresh() {
      if(this.loading)return;this.loading=true;
      try { const data=await this.api('/api/laptop');this.status(data);this.render(data.approvals); }
      catch(error){this.$('laptopNotice').textContent=error.message;}
      finally{this.loading=false;}
    }
    async receive() {
      await this.refresh();this.onPending();
      this.$('laptopApprovals').querySelector('.approval-card')?.scrollIntoView({block:'start'});
    }
    render(records) {
      const pending=records.filter(item=>item.state==='pending').length;
      this.$('approvalNotice').hidden=!pending;
      this.$('approvalCount').textContent=pending===1?'A laptop request needs your review':pending+' laptop requests need your review';
      const signature=JSON.stringify(records);if(signature===this.signature)return;this.signature=signature;
      const list=this.$('laptopApprovals');list.replaceChildren();
      this.$('laptopNotice').textContent=pending?'Review the location and requested access or change. Only these buttons can approve it.':'No requests waiting for approval.';
      for(const record of [...records].reverse()){
        const card=document.createElement('article');card.className='approval-card';card.dataset.approvalId=record.id;
        const title=document.createElement('h3');title.textContent=record.title;
        const target=document.createElement('p');target.className='approval-target';target.textContent=record.target;
        const state=document.createElement('p');state.className='approval-state';state.setAttribute('role','status');
        state.textContent=record.result?.message||record.state;
        card.append(title,target,state);
        if(record.state==='completed'&&record.result){
          const result=record.result;
          if(typeof result.text==='string'){
            const text=document.createElement('pre');text.textContent=result.text;card.append(text);
            if(result.truncated){const notice=document.createElement('p');notice.textContent='Showing the first 12,000 characters.';card.append(notice);}
          }
          if(result.items){
            const list=document.createElement('div');list.className='file-results';
            for(const item of result.items){
              const button=document.createElement('button');button.className='file-entry';
              button.textContent=(item.kind==='folder'?'Folder · ':'File · ')+item.name;
              button.disabled=item.kind!=='folder'&&!item.readable;
              button.title=item.path+(button.disabled?' · listing only':' · asks for approval');
              button.addEventListener('click',()=>this.requestAccess(item.kind==='folder'?'browse_folder':'read_file',item.path));list.append(button);
            }card.append(list);
            const note=document.createElement('p');note.className='panel-footnote';note.textContent='Up to 200 entries. Opening a subfolder or reading a file asks again.';card.append(note);
          }
        }
        if(record.state==='pending'){
          const label=document.createElement('p');label.textContent=record.access_only?'Requested access':record.tool==='write_text'?'Proposed file contents':'Proposed change';
          const preview=document.createElement('pre');preview.tabIndex=0;preview.textContent=record.content??record.preview;
          card.append(label,preview);
          if(record.backup_on_update){
            const diff=document.createElement('details');const summary=document.createElement('summary');summary.textContent='View changes from the current file';
            const text=document.createElement('pre');text.textContent=record.preview;diff.append(summary,text);card.append(diff);
          }
          const note=document.createElement('p');note.className='panel-footnote';
          note.textContent=(record.backup_on_update?'A backup of the original will be kept. ':'')+'Expires after 10 minutes. '+(record.access_only?'One-time, read-only access. Reject reads nothing.':'Reject leaves files unchanged.');
          const actions=document.createElement('div');actions.className='approval-actions';
          for(const decision of ['approve','reject']){
            const button=document.createElement('button');button.className='secondary-button';button.textContent=decision==='approve'?'Approve':'Reject';
            button.addEventListener('click',async()=>{
              actions.querySelectorAll('button').forEach(el=>el.disabled=true);
              try{const result=await this.api('/api/laptop/approvals/'+record.id,{decision});this.onResult(result.result?.conversation_text||result.result?.message||result.state);}
              catch(error){this.notify(error.message);}
              finally{this.signature='';await this.refresh();}
            });actions.append(button);
          }card.append(note,actions);
        }list.append(card);
      }
    }
  };
})();
