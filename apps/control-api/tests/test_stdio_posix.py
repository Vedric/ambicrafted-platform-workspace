"""Real POSIX descriptors: cancellation/errors must restore fd0 and release copies."""

import json
import os
import subprocess
import sys

import pytest

PROBE = """import asyncio,json,os,socket,tempfile
from plateforme.stdio_posix import entree_stdio,MAX_FRAME_BYTES
mode=os.environ['PROBE_MODE']
saved=os.dup(0)
left=right=regular=None
if mode=='socket':
 left,right=socket.socketpair();read_fd=left.fileno();write_fd=right.fileno()
elif mode=='regular-file':
 regular=tempfile.TemporaryFile();read_fd=regular.fileno();write_fd=None
else:
 read_fd,write_fd=os.pipe()
os.dup2(read_fd,0)
expected=os.fstat(0).st_ino
baseline=len(os.listdir('/proc/self/fd'))
async def main():
 loop=asyncio.get_running_loop()
 if mode=='setup-error':
  async def fail(*args):raise OSError('synthetic setup')
  loop.connect_read_pipe=fail
 for index in range(20 if mode=='repeat' else 1):
  outcome=''
  try:
   async with entree_stdio() as entry:
    assert os.read(0,1)==b''
    if mode=='cancel':
     async with asyncio.timeout(.05):await entry.readline()
    elif mode=='read-error':
     entry.reader.set_exception(OSError('synthetic read'))
     await entry.readline()
    elif mode=='oversize':
     entry.reader.feed_data(b'x'*(MAX_FRAME_BYTES+1))
     await entry.readline()
    elif mode=='eof':
     os.close(write_fd)
     assert await entry.readline()==''
    else:
     os.write(write_fd,'Hello Védric\\n'.encode())
     assert await entry.readline()=='Hello Védric\\n'
     outcome='read'
  except TimeoutError:outcome='cancelled'
  except OSError:outcome='io-error'
  except ValueError:outcome='unsupported-input' if mode=='regular-file' else 'frame-limit'
  assert os.fstat(0).st_ino==expected
  assert os.get_blocking(0)
  await asyncio.sleep(0)
  assert len(os.listdir('/proc/self/fd'))<=baseline+3
 return outcome
try:
 outcome=asyncio.run(main())
finally:
 os.dup2(saved,0);os.close(saved)
 if left is not None:left.close();right.close()
 elif regular is not None:regular.close()
 else:
  os.close(read_fd)
  if mode!='eof':os.close(write_fd)
print(json.dumps({'outcome':outcome,'fd0_restored':True,'descriptors_bounded':True}))
"""


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("read", "read"),
        ("repeat", "read"),
        ("socket", "read"),
        ("eof", ""),
        ("cancel", "cancelled"),
        ("setup-error", "io-error"),
        ("read-error", "io-error"),
        ("oversize", "frame-limit"),
        ("regular-file", "unsupported-input"),
    ],
)
def test_posix_descriptor_lifecycle(tmp_path, mode, expected):
    script = tmp_path / "probe.py"
    script.write_text(PROBE)
    env = {name: value for name, value in os.environ.items() if name in {"PATH", "HOME", "LANG"}}
    env["PROBE_MODE"] = mode
    result = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {
        "outcome": expected,
        "fd0_restored": True,
        "descriptors_bounded": True,
    }
    assert b"ResourceWarning" not in result.stderr


OUTPUT_PROBE = """import asyncio,json,os,socket,tempfile,threading
from plateforme.stdio_posix import sortie_stdio
mode=os.environ['PROBE_MODE']; saved=os.dup(1)
left=right=regular=None
if mode=='socket':
 left,right=socket.socketpair();write_fd=left.fileno();read_fd=right.fileno()
elif mode=='regular-file':
 regular=tempfile.TemporaryFile();write_fd=regular.fileno();read_fd=None
else:read_fd,write_fd=os.pipe()
os.dup2(write_fd,1);expected=os.fstat(1).st_ino
baseline=len(os.listdir('/proc/self/fd'))
async def main():
 loop=asyncio.get_running_loop()
 if mode=='setup-error':
  def fail(*args):raise OSError('synthetic writer registration')
  loop.add_writer=fail
 for index in range(20 if mode=='repeat' else 1):
  outcome=''
  try:
   async with sortie_stdio() as output:
    if mode in {'cancel','setup-error'}:
     async with asyncio.timeout(.05):await output.write('x'*1_000_000)
    elif mode=='write-error':
     os.close(read_fd)
     await output.write('synthetic-private-payload')
    else:
     os.write(1,b'incidental-output')
     assert await output.write('Hello Védric\\n')==len('Hello Védric\\n')
     await output.flush()
     assert os.read(read_fd,4096)=='Hello Védric\\n'.encode()
     outcome='write'
  except TimeoutError:outcome='cancelled'
  except OSError:outcome='io-error'
  except ValueError:outcome='unsupported-output'
  assert os.fstat(1).st_ino==expected
  assert os.get_blocking(1)
  await asyncio.sleep(0)
  assert len(os.listdir('/proc/self/fd'))<=baseline+3
  assert threading.active_count()==1
 return outcome
try:outcome=asyncio.run(main())
finally:
 os.dup2(saved,1);os.close(saved)
 if left is not None:left.close();right.close()
 elif regular is not None:regular.close()
 else:
  os.close(write_fd)
  if mode!='write-error':os.close(read_fd)
print(json.dumps({'outcome':outcome,'fd1_restored':True,'descriptors_bounded':True,'no_worker_thread':True}))
"""


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("write", "write"),
        ("repeat", "write"),
        ("socket", "write"),
        ("cancel", "cancelled"),
        ("setup-error", "io-error"),
        ("write-error", "io-error"),
        ("regular-file", "unsupported-output"),
    ],
)
def test_posix_output_lifecycle(tmp_path, mode, expected):
    script = tmp_path / "output.py"
    script.write_text(OUTPUT_PROBE)
    env = {name: value for name, value in os.environ.items() if name in {"PATH", "HOME", "LANG"}}
    env["PROBE_MODE"] = mode
    result = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {
        "outcome": expected,
        "fd1_restored": True,
        "descriptors_bounded": True,
        "no_worker_thread": True,
    }
    assert result.stderr == b"incidental-output" * (
        20 if mode == "repeat" else int(expected == "write")
    )


def test_output_setup_failure_also_restores_input(tmp_path):
    script = tmp_path / "both.py"
    script.write_text("""import asyncio,json,os,tempfile
from plateforme.stdio_posix import entree_stdio,sortie_stdio
saved_input=os.dup(0);saved_output=os.dup(1)
read_fd,write_fd=os.pipe()
with tempfile.TemporaryFile() as regular:
 os.dup2(read_fd,0);os.dup2(regular.fileno(),1)
 identities=[os.fstat(fd).st_ino for fd in (0,1)]
 baseline=len(os.listdir('/proc/self/fd'))
 async def main():
  for _ in range(20):
   try:
    async with entree_stdio(),sortie_stdio():raise AssertionError('regular output accepted')
   except ValueError:pass
   assert [os.fstat(fd).st_ino for fd in (0,1)]==identities
   assert all(os.get_blocking(fd) for fd in (0,1))
   await asyncio.sleep(0)
   assert len(os.listdir('/proc/self/fd'))<=baseline+3
 asyncio.run(main())
 os.dup2(saved_input,0);os.dup2(saved_output,1)
for fd in (saved_input,saved_output,read_fd,write_fd):os.close(fd)
print(json.dumps({'both_restored':True,'attempts':20}))
""")
    env = {name: value for name, value in os.environ.items() if name in {"PATH", "HOME", "LANG"}}
    result = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"both_restored": True, "attempts": 20}
    assert result.stderr == b""
