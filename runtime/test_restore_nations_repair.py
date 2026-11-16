import hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
from restore_nations_repair import restore

class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def package(self,member='objects/a'):
        body=b'synthetic evidence';archive=self.root/'test.tar.gz'
        with tarfile.open(archive,'w:gz') as stream:
            info=tarfile.TarInfo(member);info.size=len(body);stream.addfile(info,io.BytesIO(body))
        j={'schema':'WCPP-NATIONS-REPAIR-ARCHIVE-1','source_commit':'synthetic',
           'archives':{'test.tar.gz':{'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}},
           'files':[{'original_path':'/workspace/a.json','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'archive':'test.tar.gz','member':member}]}
        p=self.root/'index.json';p.write_text(json.dumps(j));return p
    def test_restore_and_repeat_do_not_modify_identical_evidence(self):
        p=self.package();dest=self.root/'dest';restore(self.root,p,dest)
        target=dest/'workspace/a.json';before=target.stat().st_mtime_ns
        self.assertEqual(restore(self.root,p,dest)['verified_paths'],1)
        self.assertEqual(target.stat().st_mtime_ns,before)
    def test_conflicting_existing_file_is_preserved(self):
        p=self.package();dest=self.root/'dest';target=dest/'workspace/a.json'
        target.parent.mkdir(parents=True);target.write_bytes(b'keep existing')
        with self.assertRaises(ValueError):restore(self.root,p,dest)
        self.assertEqual(target.read_bytes(),b'keep existing')
    def test_path_escape_and_tampered_archive_refused(self):
        p=self.package('../escape')
        with self.assertRaises(ValueError):restore(self.root,p,self.root/'dest')
        p=self.package();(self.root/'test.tar.gz').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):restore(self.root,p,self.root/'dest')

if __name__=='__main__':unittest.main()
