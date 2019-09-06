import subprocess
from textwrap import dedent

import os

from orangecanvas.utils.shtools import (
    python_process, temp_named_file, temp_named_dir, open_locked
)

import unittest


class Test(unittest.TestCase):
    def test_python_process(self):
        p = python_process(["-c", "print('Hello')"])
        out, _ = p.communicate()
        self.assertEqual(out.strip(), "Hello")
        self.assertEqual(p.wait(), 0)

    def test_temp_named_file(self):
        cases = [
            ("Hello", "utf-8"),
            ("Hello", "utf-16"),
        ]
        for content, encoding in cases:
            with temp_named_file(content, encoding=encoding) as fname:
                with open(fname, "r", encoding=encoding) as f:
                    c = f.read()
                    self.assertEqual(c, content)
            self.assertFalse(os.path.exists(fname))

    def test_temp_named_dir(self):
        with temp_named_dir() as name:
            self.assertTrue(os.path.isdir(name))
        self.assertFalse(os.path.exists(name))

    def test_open_locked(self):
        with temp_named_dir() as dname:
            name = os.path.join(dname, "aa")
            with open_locked(name, "w") as fw:
                fw.write("A")
                fw.flush()
                with self.assertRaises(BlockingIOError):
                    open_locked(name, "r", timeout=0)
                with self.assertRaises(BlockingIOError):
                    open_locked(name, "a+", timeout=0)
                with self.assertRaises(TimeoutError):
                    open_locked(name, "w", timeout=0.01)
                with self.assertRaises(TimeoutError):
                    open_locked(name, "a+", timeout=0.01)

            fr = open_locked(name, "r")
            self.assertEqual(fr.read(), "A")

            fr2 = open_locked(name, "r")
            with self.assertRaises(BlockingIOError):
                open_locked(name, "w", timeout=0)
            fr2.close()
            with self.assertRaises(TimeoutError):
                open_locked(name, "w", timeout=0.01)
            fr.close()

            with open_locked(name, "w+", timeout=0.01) as f:
                self.assertEqual(f.read(), "")

    def test_open_locked_process(self):
        s = dedent("""
        import sys
        from orangecanvas.utils.shtools import open_locked
        f = open_locked(sys.argv[1], "w+")
        print("OK", flush=True)
        raw_input()  # wait until killed
        """)
        with temp_named_dir() as dname:
            lockfile = os.path.join(dname, "lock")
            p = python_process(
                ["-", lockfile], stdin=subprocess.PIPE, stdout=subprocess.PIPE
            )
            p.stdin.write(s)
            p.stdin.close()

            out = p.stdout.read(2)
            assert out == "OK"
            with self.assertRaises(BlockingIOError, ):
                open_locked(lockfile, "r", timeout=0)
            p.stdout.close()
            p.kill()
            p.wait()
            with open_locked(lockfile, "w+") as f:
                pass
