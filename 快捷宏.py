import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import keyboard
import pydirectinput
import threading
import time
import json
import os
from typing import List

class MacroConfig:
    def __init__(self, name="未命名", hotkey="f8", loop_count=0, actions=None):
        self.name = name
        self.hotkey = hotkey
        self.loop_count = loop_count
        self.actions = actions if actions is not None else []
        self.thread = None
        self.running = False
        self.stop_flag = threading.Event()

    def to_dict(self):
        return {
            "name": self.name,
            "hotkey": self.hotkey,
            "loop_count": self.loop_count,
            "actions": self.actions
        }

    @staticmethod
    def from_dict(d):
        return MacroConfig(
            name=d.get("name", "未命名"),
            hotkey=d.get("hotkey", "f8"),
            loop_count=d.get("loop_count", 0),
            actions=d.get("actions", [])
        )

class MacroApp:
    CONFIG_FILE = "macro_config.json"

    def __init__(self, root):
        self.root = root
        self.root.title("多快捷键宏控制器 v4.3 (修复刷新)")
        self.root.geometry("800x600")
        self.root.attributes("-topmost", True)

        self.macros: List[MacroConfig] = []
        self.current_edit_index = 0

        if not self.load_config():
            default_actions = [
                {"type": "click", "button": "left", "delay": 0.03},
                {"type": "press", "key": "enter", "delay": 0.03},
                {"type": "typewrite", "text": "Hello", "delay": 0.03}
            ]
            self.macros.append(MacroConfig("示例宏", "f8", 0, default_actions))

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # 启动定时刷新（只刷新状态，不动编辑器）
        self.light_refresh_timer()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # ===== 页面1：操作台 =====
        self.page1 = ttk.Frame(self.notebook)
        self.notebook.add(self.page1, text="操作台（热键列表）")

        top_frame = ttk.Frame(self.page1)
        top_frame.pack(fill="x", pady=5)
        self.btn_start_all = ttk.Button(top_frame, text="启动全部热键监听", command=self.start_all_listeners)
        self.btn_start_all.pack(side="left", padx=5)
        self.btn_stop_all = ttk.Button(top_frame, text="停止全部监听", command=self.stop_all_listeners)
        self.btn_stop_all.pack(side="left", padx=5)
        self.btn_stop_macros = ttk.Button(top_frame, text="紧急停止所有宏", command=self.stop_all_macros)
        self.btn_stop_macros.pack(side="left", padx=5)

        columns = ("hotkey", "name", "status", "loop")
        self.tree = ttk.Treeview(self.page1, columns=columns, show="headings", height=15)
        self.tree.heading("hotkey", text="热键")
        self.tree.heading("name", text="宏名称")
        self.tree.heading("status", text="状态")
        self.tree.heading("loop", text="循环")
        self.tree.column("hotkey", width=100)
        self.tree.column("name", width=200)
        self.tree.column("status", width=80)
        self.tree.column("loop", width=80)
        self.tree.pack(fill="both", expand=True, pady=5)

        btn_frame1 = ttk.Frame(self.page1)
        btn_frame1.pack(fill="x", pady=5)
        ttk.Button(btn_frame1, text="前往编辑器", command=lambda: self.notebook.select(1)).pack(side="right", padx=5)
        ttk.Button(btn_frame1, text="保存配置到文件", command=self.save_config_gui).pack(side="left", padx=5)
        ttk.Button(btn_frame1, text="刷新列表", command=self.full_refresh).pack(side="left", padx=5)

        # ===== 页面2：编辑器 =====
        self.page2 = ttk.Frame(self.notebook)
        self.notebook.add(self.page2, text="宏编辑器")

        select_frame = ttk.Frame(self.page2)
        select_frame.pack(fill="x", pady=5)
        ttk.Label(select_frame, text="编辑宏:").pack(side="left")
        self.combo_macro = ttk.Combobox(select_frame, state="readonly", width=30)
        self.combo_macro.pack(side="left", padx=5)
        self.combo_macro.bind("<<ComboboxSelected>>", self.on_combo_select)
        ttk.Button(select_frame, text="新建", command=self.new_macro).pack(side="left", padx=2)
        ttk.Button(select_frame, text="删除", command=self.delete_macro).pack(side="left", padx=2)

        prop_frame = ttk.LabelFrame(self.page2, text="宏属性", padding=10)
        prop_frame.pack(fill="x", pady=5)
        ttk.Label(prop_frame, text="名称:").grid(row=0, column=0, sticky="e")
        self.entry_name = ttk.Entry(prop_frame, width=30)
        self.entry_name.grid(row=0, column=1, padx=5)
        ttk.Label(prop_frame, text="热键:").grid(row=0, column=2, sticky="e")
        self.entry_hotkey = ttk.Entry(prop_frame, width=15)
        self.entry_hotkey.grid(row=0, column=3, padx=5)
        ttk.Label(prop_frame, text="循环(0=无限):").grid(row=1, column=0, sticky="e")
        self.entry_loop = ttk.Entry(prop_frame, width=10)
        self.entry_loop.grid(row=1, column=1, padx=5, sticky="w")

        action_frame = ttk.LabelFrame(self.page2, text="动作序列 (JSON)", padding=10)
        action_frame.pack(fill="both", expand=True, pady=5)
        self.txt_actions = scrolledtext.ScrolledText(action_frame, height=12, font=("Consolas", 10))
        self.txt_actions.pack(fill="both", expand=True)
        btn_af = ttk.Frame(action_frame)
        btn_af.pack(fill="x", pady=5)
        ttk.Button(btn_af, text="保存此宏", command=self.save_current_macro).pack(side="left", padx=2)
        ttk.Button(btn_af, text="测试运行", command=self.test_run_macro).pack(side="left", padx=2)
        ttk.Button(btn_af, text="停止此宏", command=self.stop_current_macro).pack(side="left", padx=2)
        ttk.Button(btn_af, text="格式化JSON", command=self.format_actions_json).pack(side="left", padx=2)

        self.full_refresh()   # 首次加载编辑器

    # ---------- 配置保存/加载 ----------
    def save_config_to_file(self):
        try:
            data = [m.to_dict() for m in self.macros]
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"无法保存配置文件：{str(e)}")
            return False

    def load_config(self) -> bool:
        if not os.path.exists(self.CONFIG_FILE):
            return False
        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return False
            self.macros = [MacroConfig.from_dict(item) for item in data]
            return True
        except Exception as e:
            messagebox.showwarning("加载配置", f"读取配置文件失败：{str(e)}")
            return False

    def save_config_gui(self):
        if self.save_config_to_file():
            messagebox.showinfo("成功", "配置已保存到 " + self.CONFIG_FILE)

    # ---------- 刷新逻辑 ----------
    def full_refresh(self):
        """完全刷新：更新树、下拉列表，并重新加载当前宏到编辑器"""
        # 更新树
        for row in self.tree.get_children():
            self.tree.delete(row)
        for m in self.macros:
            status = "运行中" if m.running else "空闲"
            loop_text = "无限" if m.loop_count == 0 else str(m.loop_count)
            self.tree.insert("", "end", values=(m.hotkey, m.name, status, loop_text))
        
        # 更新下拉列表并加载编辑器
        self.update_combo_list()
        if self.macros and self.current_edit_index >= 0:
            self.load_macro_to_editor(self.current_edit_index)

    def light_refresh(self):
        """轻量刷新：仅更新树和下拉列表的文字状态，不触碰编辑器内容"""
        # 更新树
        for row in self.tree.get_children():
            self.tree.delete(row)
        for m in self.macros:
            status = "运行中" if m.running else "空闲"
            loop_text = "无限" if m.loop_count == 0 else str(m.loop_count)
            self.tree.insert("", "end", values=(m.hotkey, m.name, status, loop_text))
        
        # 更新下拉列表（仅更新选项文字，不重新加载编辑器）
        names = [f"{m.name} ({m.hotkey})" for m in self.macros]
        self.combo_macro['values'] = names
        if self.macros and self.current_edit_index >= 0:
            # 保持当前选中项，但不触发编辑器加载
            self.combo_macro.current(self.current_edit_index)

    def light_refresh_timer(self):
        """定时调用轻量刷新"""
        self.light_refresh()
        self.root.after(500, self.light_refresh_timer)

    def update_combo_list(self):
        """仅更新下拉列表的选项值（由 full_refresh 调用）"""
        names = [f"{m.name} ({m.hotkey})" for m in self.macros]
        self.combo_macro['values'] = names
        if self.macros:
            if self.current_edit_index < 0 or self.current_edit_index >= len(self.macros):
                self.current_edit_index = 0
            self.combo_macro.current(self.current_edit_index)

    def load_macro_to_editor(self, index):
        """将宏数据加载到编辑控件（会覆盖当前编辑内容）"""
        if 0 <= index < len(self.macros):
            macro = self.macros[index]
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, macro.name)
            self.entry_hotkey.delete(0, tk.END)
            self.entry_hotkey.insert(0, macro.hotkey)
            self.entry_loop.delete(0, tk.END)
            self.entry_loop.insert(0, str(macro.loop_count))
            self.txt_actions.delete(1.0, tk.END)
            self.txt_actions.insert(tk.END, json.dumps(macro.actions, indent=4, ensure_ascii=False))
            self.current_edit_index = index

    def on_combo_select(self, event=None):
        """用户手动选择下拉框时加载宏"""
        idx = self.combo_macro.current()
        if idx >= 0:
            self.load_macro_to_editor(idx)

    # ---------- 宏编辑 ----------
    def new_macro(self):
        new_m = MacroConfig("新建宏", "f1", 1, [])
        self.macros.append(new_m)
        self.current_edit_index = len(self.macros) - 1
        self.full_refresh()   # 完全刷新，加载新宏编辑器

    def delete_macro(self):
        if self.current_edit_index == -1 or not self.macros:
            return
        macro = self.macros[self.current_edit_index]
        if messagebox.askyesno("确认", f"删除宏 '{macro.name}'？"):
            self.stop_macro(self.current_edit_index)
            try:
                keyboard.remove_hotkey(macro.hotkey)
            except:
                pass
            del self.macros[self.current_edit_index]
            if self.macros:
                self.current_edit_index = min(self.current_edit_index, len(self.macros)-1)
            else:
                self.current_edit_index = -1
            self.full_refresh()

    def save_current_macro(self):
        if self.current_edit_index == -1:
            return
        macro = self.macros[self.current_edit_index]

        new_name = self.entry_name.get().strip()
        new_hotkey = self.entry_hotkey.get().strip()
        loop_str = self.entry_loop.get()
        raw_actions = self.txt_actions.get(1.0, tk.END).strip()

        if not new_name:
            messagebox.showerror("错误", "名称不能为空")
            return

        try:
            loop = int(loop_str)
            if loop < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "循环次数必须为非负整数 (0 表示无限)")
            return

        try:
            actions = json.loads(raw_actions)
            if not isinstance(actions, list):
                raise ValueError("动作列表必须是一个 JSON 数组")
        except Exception as e:
            messagebox.showerror("JSON格式错误", f"动作序列无效:\n{str(e)}")
            return

        # 所有验证通过，修改宏对象
        macro.name = new_name
        macro.hotkey = new_hotkey
        macro.loop_count = loop
        macro.actions = actions

        self.full_refresh()   # 保存后完全刷新界面（包括重新加载编辑器，保持显示最新）
        messagebox.showinfo("成功", "宏已保存！")

    def format_actions_json(self):
        try:
            raw = self.txt_actions.get(1.0, tk.END)
            parsed = json.loads(raw)
            formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
            self.txt_actions.delete(1.0, tk.END)
            self.txt_actions.insert(tk.END, formatted)
        except Exception as e:
            messagebox.showerror("格式化失败", str(e))

    # ---------- 宏执行控制 ----------
    def test_run_macro(self):
        if self.current_edit_index == -1:
            return
        self.save_current_macro()   # 会自动调用 full_refresh
        macro = self.macros[self.current_edit_index]
        if macro.running:
            messagebox.showinfo("提示", "该宏已在运行，请先停止")
            return
        self.start_macro_execution(self.current_edit_index)

    def stop_current_macro(self):
        if self.current_edit_index == -1:
            return
        self.stop_macro(self.current_edit_index)

    def start_macro_execution(self, index):
        macro = self.macros[index]
        if macro.running:
            return
        macro.stop_flag.clear()
        macro.running = True
        macro.thread = threading.Thread(target=self.macro_worker, args=(index,), daemon=True)
        macro.thread.start()

    def stop_macro(self, index):
        macro = self.macros[index]
        macro.stop_flag.set()
        macro.running = False

    def stop_all_macros(self):
        for i in range(len(self.macros)):
            self.stop_macro(i)

    def macro_worker(self, index):
        macro = self.macros[index]
        loop_count = macro.loop_count
        iteration = 0
        try:
            while not macro.stop_flag.is_set():
                for action in macro.actions:
                    if macro.stop_flag.is_set():
                        break
                    try:
                        if action["type"] == "click":
                            pydirectinput.click(button=action.get("button", "left"))
                        elif action["type"] == "press":
                            pydirectinput.press(action["key"])
                        elif action["type"] == "typewrite":
                            pydirectinput.typewrite(action["text"], interval=action.get("interval", 0.0))
                        else:
                            print(f"未知动作: {action['type']}")
                    except KeyError as e:
                        self.root.after(0, messagebox.showerror, "错误", f"动作缺少字段: {e}")
                        macro.stop_flag.set()
                        break
                    except Exception as e:
                        self.root.after(0, messagebox.showerror, "执行错误", str(e))
                        macro.stop_flag.set()
                        break
                    if not macro.stop_flag.is_set():
                        time.sleep(action.get("delay", 0.03))
                if loop_count > 0:
                    iteration += 1
                    if iteration >= loop_count:
                        break
        finally:
            macro.running = False

    # ---------- 全局热键管理 ----------
    def start_all_listeners(self):
        self.safe_unhook_all()
        success = 0
        for i, macro in enumerate(self.macros):
            hotkey = macro.hotkey
            if not hotkey:
                continue
            try:
                keyboard.add_hotkey(hotkey, lambda idx=i: self.on_hotkey_trigger(idx))
                success += 1
            except Exception as e:
                messagebox.showwarning("注册失败", f"热键 {hotkey} 注册失败: {e}")
        messagebox.showinfo("完成", f"已启动 {success} 个热键监听！")

    def stop_all_listeners(self):
        self.safe_unhook_all()
        messagebox.showinfo("提示", "已停止全部热键监听")

    def safe_unhook_all(self):
        try:
            keyboard.unhook_all_hotkeys()
        except AttributeError:
            try:
                keyboard.remove_all_hotkeys()
            except:
                keyboard.unhook_all()

    def on_hotkey_trigger(self, index):
        macro = self.macros[index]
        if macro.running:
            self.stop_macro(index)
        else:
            self.start_macro_execution(index)

    def on_close(self):
        self.save_config_to_file()
        self.stop_all_macros()
        self.safe_unhook_all()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = MacroApp(root)
    root.mainloop()
