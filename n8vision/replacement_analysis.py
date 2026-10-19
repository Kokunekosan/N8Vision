"""Invalidate path-owned pixel evidence after a known successful overwrite."""
def invalidate(c,path,size,mtime):
 counts={}
 for table in ('observations','embeddings','corrections'):
  if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
   counts[table]=c.execute(f'DELETE FROM {table} WHERE path=?',(str(path),)).rowcount
 c.execute('INSERT INTO tracked_files(path,size,mtime,orphaned,last_seen) VALUES(?,?,?,0,unixepoch()) ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,orphaned=0,last_seen=unixepoch()', (str(path),size,mtime))
 if 'sha256' in {row[1] for row in c.execute('PRAGMA table_info(tracked_files)')}:c.execute('UPDATE tracked_files SET sha256=NULL WHERE path=?',(str(path),))
 return counts
