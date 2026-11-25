#!/usr/bin/env python3
"""Re-run the separately authored R22 cross-check on #61's pinned parents."""
import argparse,hashlib,os,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
 root=a.data_root.resolve(); source=a.source.resolve(); r21=root/'workspace-updates/20261125-r21-score-dependence'; r11=r21/'inputs/r11'; ref=r21/'replay/reference'
 lock=__import__('json').loads((r21/'source-lock.json').read_bytes())
 if sha(ref/'inputs.json')!='4426c16417eab543aedd54001357c846f10a6569fe9084a12333e260f611487d':raise ValueError('R21 historical inputs SHA mismatch')
 if sha(r11/'extension.tar.gz')!=__import__('json').loads((ref/'inputs.json').read_bytes())['extension_sha256']:raise ValueError('R11 extension parent differs')
 env=dict(os.environ,PYTHONPATH=str(source/'runtime'),PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',OPENBLAS_NUM_THREADS='1',OPENBLAS_CORETYPE='Haswell',NPY_DISABLE_CPU_FEATURES='AVX512F',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
 with tempfile.TemporaryDirectory(prefix='r22-independent-') as t:
  out=Path(t)/'actual.json'; cmd=[sys.executable,'-B',str(HERE/'r22_independent.py'),str(root/'workspace-updates'),str(ref),str(r11),str(out)]
  subprocess.run(cmd,env=env,check=True)
  expected=HERE/'expected.json'
  if out.read_bytes()!=expected.read_bytes():raise ValueError('independent R22 result bytes differ from preserved cross-check')
  print({'verified':True,'result_sha256':sha(expected),'r21_source_commit':lock['source_commit'],'r21_inputs_sha256':sha(ref/'inputs.json')})
if __name__=='__main__':main()
