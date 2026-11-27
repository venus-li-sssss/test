$src = @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lp, IntPtr p);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static void Dump() {
    EnumWindows((h, p) => {
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      uint pid; GetWindowThreadProcessId(h, out pid);
      string t = sb.ToString();
      if (t.Length > 0) Console.WriteLine(t + "   [pid=" + pid + "]");
      return true;
    }, IntPtr.Zero);
  }
}
"@
Add-Type -TypeDefinition $src
[W]::Dump()
