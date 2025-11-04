#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicativo de Lembretes - versão estável
Funcionalidades principais:
- Adicionar / editar / excluir / ativar-desativar lembretes
- Persistência em JSON (lembretes.json)
- Notificações do sistema via plyer (se disponível)
- Popup Tkinter sempre exibido (disparado na thread principal)
- Modo Demo para testes rápidos
"""
import json, os, threading, time
from datetime import datetime, date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from plyer import notification
    PLYER_OK = True
except Exception:
    PLYER_OK = False

ARQ_JSON = "lembretes.json"

def validar_horario(hhmm: str) -> bool:
    try:
        datetime.strptime(hhmm, "%H:%M")
        return True
    except Exception:
        return False

def agora_hhmm() -> str:
    return datetime.now().strftime("%H:%M")

def hoje_iso() -> str:
    return date.today().isoformat()

class Store:
    def __init__(self, caminho=ARQ_JSON):
        self.caminho = caminho
        self.dados = {"lembretes": []}
        self.carregar()

    def carregar(self):
        if os.path.exists(self.caminho):
            try:
                with open(self.caminho, "r", encoding="utf-8") as f:
                    self.dados = json.load(f)
            except Exception:
                self.dados = {"lembretes": []}
        else:
            self.salvar()

    def salvar(self):
        with open(self.caminho, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=2)

    def listar(self):
        return self.dados.get("lembretes", [])

    def adicionar(self, texto, horario, ativo=True):
        item = {
            "id": int(datetime.now().timestamp() * 1000),
            "texto": texto.strip(),
            "horario": horario.strip(),
            "ativo": bool(ativo),
            "ultimo_disparo_em": None
        }
        self.dados.setdefault("lembretes", []).append(item)
        self.salvar()
        return item

    def atualizar(self, item_id, **campos):
        for it in self.dados.get("lembretes", []):
            if it["id"] == item_id:
                it.update(campos)
                self.salvar()
                return it
        raise KeyError("Item não encontrado")

    def remover(self, item_id):
        self.dados["lembretes"] = [x for x in self.dados.get("lembretes", []) if x["id"] != item_id]
        self.salvar()

    def exportar(self, caminho):
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=2)

class Scheduler(threading.Thread):
    def __init__(self, store, ui_callback_status=None, ui_callback_popup=None, intervalo=5):
        super().__init__(daemon=True)
        self.store = store
        self.intervalo = max(1, int(intervalo))
        self._stop = threading.Event()
        self.ui_callback_status = ui_callback_status
        self.ui_callback_popup = ui_callback_popup
        self.demo_speed = False

    def parar(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self.verificar()
            except Exception as e:
                print("Erro Scheduler:", e)
            time.sleep(self.intervalo if not self.demo_speed else 1)

    def verificar(self):
        hh = agora_hhmm()
        hoje = hoje_iso()
        for it in list(self.store.listar()):
            if not it.get("ativo", True):
                continue
            if not validar_horario(it.get("horario", "")):
                continue
            if it.get("ultimo_disparo_em") == hoje:
                continue
            if it["horario"] == hh:
                # marca disparo e solicita popup via callback na UI
                self.store.atualizar(it["id"], ultimo_disparo_em=hoje)
                titulo = "Lembrete"
                mensagem = f"{it['horario']} - {it['texto']}"
                # Tenta notificação nativa
                if PLYER_OK:
                    try:
                        notification.notify(title=titulo, message=mensagem, timeout=10)
                    except Exception:
                        pass
                # solicita popup para UI thread
                if self.ui_callback_popup:
                    try:
                        self.ui_callback_popup(titulo, mensagem)
                    except Exception as e:
                        print("Erro ao solicitar popup:", e)
        if self.ui_callback_status:
            try:
                self.ui_callback_status(f"Monitorando — {hh}")
            except Exception:
                pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lembretes")
        self.resizable(False, False)
        self.store = Store()
        self.criar_widgets()
        self.preencher_lista()
        self.scheduler = Scheduler(self.store, ui_callback_status=self.atualizar_status, ui_callback_popup=self.popup_lembrete)
        self.scheduler.start()

    def criar_widgets(self):
        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Lembrete:").grid(row=0, column=0, sticky="w", **pad)
        self.ent_texto = ttk.Entry(frm, width=40); self.ent_texto.grid(row=0, column=1, columnspan=3, **pad)

        ttk.Label(frm, text="Horário (HH:MM):").grid(row=1, column=0, sticky="w", **pad)
        self.ent_horario = ttk.Entry(frm, width=10); self.ent_horario.grid(row=1, column=1, sticky="w", **pad)
        self.btn_add = ttk.Button(frm, text="Adicionar", command=self.adicionar); self.btn_add.grid(row=1, column=2, **pad)
        self.btn_demo = ttk.Button(frm, text="Modo Demo", command=self.ativar_demo); self.btn_demo.grid(row=1, column=3, **pad)

        ttk.Label(frm, text="Buscar:").grid(row=2, column=0, sticky="w", **pad)
        self.ent_busca = ttk.Entry(frm, width=20); self.ent_busca.grid(row=2, column=1, sticky="w", **pad)
        self.ent_busca.bind("<KeyRelease>", lambda e: self.preencher_lista())

        self.cmb_ordenar = ttk.Combobox(frm, values=["Horário", "Texto"], width=12, state="readonly"); self.cmb_ordenar.current(0); self.cmb_ordenar.grid(row=2, column=2, **pad); self.cmb_ordenar.bind("<<ComboboxSelected>>", lambda e: self.preencher_lista())

        self.tree = ttk.Treeview(frm, columns=("horario","texto","ativo"), show="headings", height=10)
        self.tree.heading("horario", text="Horário"); self.tree.heading("texto", text="Lembrete"); self.tree.heading("ativo", text="Ativo")
        self.tree.column("horario", width=80, anchor="center"); self.tree.column("texto", width=320); self.tree.column("ativo", width=50, anchor="center")
        self.tree.grid(row=3, column=0, columnspan=4, padx=10, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.btn_editar = ttk.Button(frm, text="Editar", command=self.editar, state="disabled"); self.btn_editar.grid(row=4, column=0, **pad)
        self.btn_toggle = ttk.Button(frm, text="Ativar/Desativar", command=self.toggle, state="disabled"); self.btn_toggle.grid(row=4, column=1, **pad)
        self.btn_excluir = ttk.Button(frm, text="Excluir", command=self.excluir, state="disabled"); self.btn_excluir.grid(row=4, column=2, **pad)
        self.btn_export = ttk.Button(frm, text="Exportar JSON", command=self.exportar); self.btn_export.grid(row=4, column=3, **pad)

        self.status = ttk.Label(self, text="Pronto", anchor="w"); self.status.grid(row=5, column=0, sticky="ew", padx=10, pady=(0,8))

    def atualizar_status(self, txt):
        try:
            self.status.config(text=txt)
        except Exception:
            pass

    def popup_lembrete(self, titulo, mensagem):
        # garantir execução na thread principal via after
        self.after(0, lambda: messagebox.showinfo(titulo, mensagem))

    def on_select(self, event=None):
        sel = self._selecionado()
        estado = "normal" if sel else "disabled"
        for b in (self.btn_editar, self.btn_toggle, self.btn_excluir):
            b.config(state=estado)

    def _selecionado(self):
        cur = self.tree.selection()
        if not cur:
            return None
        item = self.tree.item(cur[0])
        # id armazenado como 4º valor
        return int(item["values"][3]) if len(item["values"]) > 3 else None

    def preencher_lista(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        itens = list(self.store.listar())
        q = self.ent_busca.get().strip().lower()
        if q:
            itens = [x for x in itens if q in x["texto"].lower()]
        if self.cmb_ordenar.get() == "Horário":
            itens.sort(key=lambda x: x["horario"])
        else:
            itens.sort(key=lambda x: x["texto"].lower())
        for it in itens:
            self.tree.insert("", "end", values=(it["horario"], it["texto"], "✔" if it.get("ativo", True) else "—", it["id"]))
        self.on_select()

    def adicionar(self):
        txt = self.ent_texto.get().strip()
        hh = self.ent_horario.get().strip()
        if not txt:
            messagebox.showwarning("Atenção", "Digite o texto do lembrete.")
            return
        if not validar_horario(hh):
            messagebox.showwarning("Atenção", "Informe o horário no formato HH:MM (24h).")
            return
        self.store.adicionar(txt, hh, True)
        self.ent_texto.delete(0, tk.END); self.ent_horario.delete(0, tk.END)
        self.preencher_lista()

    def editar(self):
        sel = self._selecionado()
        if not sel:
            return
        itens = [x for x in self.store.listar() if x["id"] == sel]
        if not itens:
            return
        it = itens[0]
        win = tk.Toplevel(self); win.title("Editar"); win.resizable(False, False)
        ttk.Label(win, text="Lembrete:").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        ent_t = ttk.Entry(win, width=42); ent_t.insert(0, it["texto"]); ent_t.grid(row=0, column=1, padx=10, pady=6)
        ttk.Label(win, text="Horário (HH:MM):").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        ent_h = ttk.Entry(win, width=10); ent_h.insert(0, it["horario"]); ent_h.grid(row=1, column=1, padx=10, pady=6, sticky="w")
        def salvar():
            ntxt = ent_t.get().strip(); nh = ent_h.get().strip()
            if not ntxt or not validar_horario(nh):
                messagebox.showwarning("Atenção", "Preencha corretamente.")
                return
            self.store.atualizar(sel, texto=ntxt, horario=nh); win.destroy(); self.preencher_lista()
        ttk.Button(win, text="Salvar", command=salvar).grid(row=2, column=0, columnspan=2, pady=10)

    def toggle(self):
        sel = self._selecionado(); 
        if not sel: return
        itens = [x for x in self.store.listar() if x["id"] == sel]
        if not itens: return
        it = itens[0]
        self.store.atualizar(sel, ativo=not it.get("ativo", True))
        self.preencher_lista()

    def excluir(self):
        sel = self._selecionado()
        if not sel: return
        if messagebox.askyesno("Confirmar", "Excluir o lembrete selecionado?"):
            self.store.remover(sel); self.preencher_lista()

    def exportar(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if caminho:
            self.store.exportar(caminho); messagebox.showinfo("Exportar", "Exportado com sucesso.")

    def ativar_demo(self):
        agora = datetime.now()
        exemplos = [
            ("Beber água", (agora + timedelta(minutes=1)).strftime("%H:%M")),
            ("Alongar as costas", (agora + timedelta(minutes=2)).strftime("%H:%M")),
            ("Enviar relatório", (agora + timedelta(minutes=3)).strftime("%H:%M")),
        ]
        for txt, hh in exemplos:
            self.store.adicionar(txt, hh, True)
        self.scheduler.demo_speed = True
        self.preencher_lista()
        messagebox.showinfo("Modo Demo", "Exemplos adicionados. Aguarde as notificações.")

    def on_close(self):
        try:
            self.scheduler.parar()
        except Exception:
            pass
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
