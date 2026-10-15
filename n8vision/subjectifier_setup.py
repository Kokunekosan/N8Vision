"""Prepare optional research backends without downgrading Vision's environment."""
import argparse,json,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
SOURCES={
 'partglee':('PartGLEE','ProvenceStar/PartGLEE','8c6b83e0be076e8fe640943096059ee5c180de0e'),
 'langhops':('LangHOPS','y9miao/LangHOPS-release','591a864bd1eb7ad08ad01fd5d310ae8bd7380957'),
}
SUPPORT=['gdown','fvcore','iopath','omegaconf','lvis','pycocotools','fairscale','yacs','hydra-core','cloudpickle','termcolor','tabulate','antlr4-python3-runtime','portalocker','beautifulsoup4','soupsieve','sentencepiece','peft']

def patch(repo):
 p=repo/'projects/PartGLEE/partglee/models/pixel_decoder/ops/functions/ms_deform_attn_func.py';text=p.read_text()
 if '    raise ModuleNotFoundError(info_string)' in text:
  text=text.replace('    raise ModuleNotFoundError(info_string)','    MSDA = None',1).replace('        ctx.im2col_step = im2col_step','        if MSDA is None: raise RuntimeError("Use torch deformable attention fallback")\n        ctx.im2col_step = im2col_step',1);p.write_text(text)
 for p in repo.rglob('transform.py'):
  text=p.read_text()
  if 'Image.LINEAR' in text:p.write_text(text.replace('Image.LINEAR','Image.Resampling.BILINEAR'))
 p=repo/'projects/PartGLEE/partglee/models/PartGLEE_Model.py';text=p.read_text().replace('self.tokenizer.batch_encode_plus(', 'self.tokenizer(')
 text=re.sub(r"(all_logits\[.*\] = (?:top_object_outputs|top_part_outputs)\['pred_logits'\])(?!\.to)",r"\1.to(all_logits.dtype)",text)
 text=text.replace('resize_token_embeddings(len(self.llm_tokenizer))','resize_token_embeddings(len(self.llm_tokenizer), mean_resizing=False)').replace('resize_token_embeddings(len(self.llm_processor.tokenizer))','resize_token_embeddings(len(self.llm_processor.tokenizer), mean_resizing=False)')
 # The reconstruction checkpoint contains the trained PaliGemma parameters.
 # Fetch its licensed metadata/tokenizer, but don't download a second full set
 # of base weights solely to replace them immediately with that checkpoint.
 if 'PaliGemmaForConditionalGeneration.from_pretrained(self.llm_id)' in text:
  text=text.replace('from transformers import  PaliGemmaProcessor, PaliGemmaForConditionalGeneration, AutoTokenizer','from transformers import AutoConfig, PaliGemmaProcessor, PaliGemmaForConditionalGeneration, AutoTokenizer')
  text=text.replace('PaliGemmaForConditionalGeneration.from_pretrained(self.llm_id)','PaliGemmaForConditionalGeneration._from_config(AutoConfig.from_pretrained(self.llm_id), torch_dtype=torch.float16)')
 p.write_text(text)
 p=repo/'projects/PartGLEE/partglee/PartGLEE.py';text=p.read_text().replace("[binput['dataset_name'] for binput in batched_inputs]","[binput.get('dataset_name','custom') for binput in batched_inputs]")
 p.write_text(text)

def prepare(root,engine):
 import torch
 if not torch.cuda.is_available():raise RuntimeError('This optional reconstruction setup currently requires an NVIDIA CUDA GPU')
 root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True);deps=root/'deps'
 subprocess.run([sys.executable,'-m','pip','install','--target',str(deps),'--no-deps',*SUPPORT],check=True)
 subprocess.run([sys.executable,'-m','pip','install','--target',str(root/'legacy'),'--no-deps','--only-binary=:all:','transformers==4.48.2','tokenizers==0.21.4','huggingface_hub==0.29.3','peft==0.6.2'],check=True)
 sys.path.insert(0,str(deps));import requests,gdown
 from huggingface_hub import snapshot_download,hf_hub_download
 name,project,revision=SOURCES[engine];repo=root/name
 if not repo.is_dir():
  with tempfile.TemporaryDirectory(dir=root) as raw:
   temp=Path(raw);archive=temp/'source.zip'
   with requests.get(f'https://codeload.github.com/{project}/zip/{revision}',stream=True,timeout=(15,60)) as response:
    response.raise_for_status()
    with archive.open('wb') as stream:
     for chunk in response.iter_content(1024*1024):stream.write(chunk)
   with zipfile.ZipFile(archive) as z:
    for member in z.infolist():
     target=(temp/member.filename).resolve()
     if not target.is_relative_to(temp.resolve()):raise ValueError('Unsafe source archive path')
    if z.testzip():raise ValueError('Source archive failed CRC check')
    z.extractall(temp)
   extracted=temp/(project.split('/')[-1]+'-'+revision);shutil.move(str(extracted),str(repo))
  (repo/'.n8vision-source.json').write_text(json.dumps({'project':project,'revision':revision}))
 patch(repo)
 clip=root/'clip-download'
 snapshot_download('Junfeng5/GLEE_demo',repo_type='space',allow_patterns=['GLEE/clip_vit_base_patch32/*'],local_dir=clip)
 shutil.copytree(clip/'GLEE/clip_vit_base_patch32',repo/'projects/PartGLEE/clip_vit_base_patch32',dirs_exist_ok=True)
 weights=root/'weights';weights.mkdir(exist_ok=True)
 name,id=('PartGLEE-RN50.pth','1SK0HsYXBcTvprFAxqxH-lgpkgV67B4UZ') if engine=='partglee' else ('LangHOPS-full.pth','1VmzWt9CW4td3GBJCzSz7xVjWmygXemE3')
 target=weights/name
 if not target.is_file():gdown.download(id=id,output=str(target),quiet=False,timeout=(15,60))
 if engine=='langhops':
  print('LangHOPS is an optional noncommercial research backend; upstream terms remain in its source folder.',flush=True)
  # This requires the user's own approved Hugging Face account. Never accepts
  # a token through Vision's web API or silently bypasses the gated repository.
  hf_hub_download('google/paligemma2-3b-pt-448','config.json')
 test=Path(__file__).resolve().parent.parent/'static/N8_256.png'
 request=root/(engine+'-verification-input.json');request.write_text(json.dumps({'paths':[str(test)]}),encoding='utf-8')
 subprocess.run([sys.executable,str(Path(__file__).with_name('subjectifier_worker.py')),'--root',str(root),'--engine',engine,'--request',str(request),'--output',str(root/(engine+'-verification.json'))],check=True)
 print(engine+' prepared and pretrained inference verified',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=list(SOURCES),required=True);parser.add_argument('--root',default=str(Path(__file__).resolve().parent.parent/'cache/subjectifier'));args=parser.parse_args();prepare(args.root,args.backend)
