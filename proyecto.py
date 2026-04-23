#Este aplicativo tiene un dashboard para visualizar CPU, RAM, núcleos y sistema en tiempo real. Incluye procesamiento de imágenes y un log de ejecución donde verás cuánto tiempo tardó cada modelo de concurrencia en procesar cada imagen
#El log también muestra información sobre la imagen más rápida y el estado de la RAM y CPU antes y después de la ejecución. Al finalizar los tres modelos, aparecerá una tabla comparativa de consumo. Se sugiere correrlo en Spyder 6 para no instalar nada extra, te recomiiendo crear una carpeta para cada modelo

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import multiprocessing
from multiprocessing import Lock
import psutil
import time
import os
from PIL import Image
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

# ──────────────────────────────────────────────
# Paleta pastel
# ──────────────────────────────────────────────
BG        = "#F5F0FF"   # fondo principal
PANEL_BG  = "#FFFFFF"
ACCENT1   = "#C9B8F5"   # violeta pastel
ACCENT2   = "#B8DCF5"   # azul pastel
ACCENT3   = "#F5C8D4"   # rosa pastel
ACCENT4   = "#B8F5D8"   # verde pastel
ACCENT5   = "#F5E8B8"   # amarillo pastel
BTN_SEQ   = "#D4A5D4"   # botón secuencial
BTN_THR   = "#A5C8E8"   # botón hilos
BTN_PRO   = "#A5D4B8"   # botón procesos
BTN_FG    = "#3A3A5C"
TITLE_FG  = "#4A3F7A"
TEXT_FG   = "#3A3A5C"
GRAPH_CPU = "#B07FE0"
GRAPH_RAM = "#7FB5E0"

# ──────────────────────────────────────────────
# Tarea de cómputo intensivo (CPU-bound)
# ──────────────────────────────────────────────
def tarea_cpu():
    x = 0
    for i in range(10_000_000):
        x += i * i
    return x


def convertir_gris(ruta_imagen):
    """Convierte una imagen a escala de grises y la guarda como _gray."""
    try:
        img = Image.open(ruta_imagen).convert("L")
        base, ext = os.path.splitext(ruta_imagen)
        out = base + "_gray" + ext
        img.save(out)
        return out
    except Exception as e:
        return f"ERROR: {e}"


# Función top-level necesaria para multiprocessing
def _convertir_gris_worker(path):
    return convertir_gris(path)

def _convertir_gris_worker_timed(path):
    """Retorna (nombre, tiempo_ms, resultado) para multiprocessing."""
    import time as _time
    nombre = os.path.basename(path)
    t0 = _time.perf_counter()
    r  = convertir_gris(path)
    t1 = _time.perf_counter() - t0
    return (nombre, t1, r)


# ──────────────────────────────────────────────
# Aplicación principal
# ──────────────────────────────────────────────
class MonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Recursos  •  Lab Arquitectura de Computadores")
        self.root.configure(bg=BG)
        self.root.geometry("1200x800")
        self.root.minsize(900, 650)

        # Estado
        self.running      = True
        self.cpu_history  = []
        self.ram_history  = []
        self.fotos        = []
        self.metodo_var   = tk.StringVar(value="")
        self.lock_gui     = threading.Lock()
        self.task_lock    = threading.Lock()
        self.semaforo     = threading.Semaphore(multiprocessing.cpu_count())
        self.tiempo_inicio = None
        self.proceso_activo = False
        self.historial_comparativo = {}   # {metodo: {elapsed, t_min, t_max, t_prom, cpu_delta, ram_delta, ok, err}}

        self._build_ui()
        self._start_monitor()

    # ──────────────────────────────────────────
    # Construcción de la UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        # ── Título ──────────────────────────────
        header = tk.Frame(self.root, bg=ACCENT1, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="🖥  Monitor de Recursos del Sistema",
                 font=("Segoe UI", 18, "bold"), bg=ACCENT1, fg=TITLE_FG).pack()
        tk.Label(header,
                 text="Laboratorio de Arquitectura de Computadores  •  Concurrencia en tiempo real",
                 font=("Segoe UI", 9), bg=ACCENT1, fg=TITLE_FG).pack()

        # ── Contenedor principal (3 filas) ──────
        main = tk.Frame(self.root, bg=BG)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        main.rowconfigure(1, weight=1)   # fila del log se expande
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=1)

        # ─── FILA 0: 3 tarjetas métricas ────────
        self._build_metrics_row(main)

        # ─── FILA 1: Gráfica + Log (50/50) ──────
        self._build_center_row(main)

        # ─── FILA 2: Imágenes + Botones + Progreso
        self._build_bottom_row(main)

    def _card(self, parent, row, col, title, accent, rowspan=1, colspan=1, fill="both", expand=True, sticky="nsew"):
        """Crea una tarjeta con borde de color."""
        outer = tk.Frame(parent, bg=accent, padx=2, pady=2)
        outer.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan,
                   padx=5, pady=5, sticky=sticky)
        inner = tk.Frame(outer, bg=PANEL_BG)
        inner.pack(fill=fill, expand=expand)
        if title:
            tk.Label(inner, text=title, font=("Segoe UI", 10, "bold"),
                     bg=PANEL_BG, fg=TITLE_FG).pack(anchor="w", padx=10, pady=(8, 2))
        return inner

    # ── Fila 0: métricas ──────────────────────
    def _build_metrics_row(self, parent):
        parent.rowconfigure(0, weight=0)

        # ─ CPU Total ─
        c1 = self._card(parent, 0, 0, "⚡ CPU Total", ACCENT1)
        self.lbl_cpu = tk.Label(c1, text="0 %", font=("Segoe UI", 34, "bold"),
                                bg=PANEL_BG, fg=GRAPH_CPU)
        self.lbl_cpu.pack(pady=(4, 2))
        self.bar_cpu = ttk.Progressbar(c1, orient="horizontal",
                                       mode="determinate", maximum=100)
        self.bar_cpu.pack(fill="x", padx=14, pady=(0, 4))
        self.lbl_cpu_val = tk.Label(c1, text="Uso del procesador",
                                    font=("Segoe UI", 8), bg=PANEL_BG, fg=TEXT_FG)
        self.lbl_cpu_val.pack(pady=(0, 8))

        # ─ RAM ─
        c2 = self._card(parent, 0, 1, "🧠 RAM", ACCENT2)
        self.lbl_ram = tk.Label(c2, text="0 %", font=("Segoe UI", 34, "bold"),
                                bg=PANEL_BG, fg=GRAPH_RAM)
        self.lbl_ram.pack(pady=(4, 2))
        self.bar_ram = ttk.Progressbar(c2, orient="horizontal",
                                       mode="determinate", maximum=100)
        self.bar_ram.pack(fill="x", padx=14, pady=(0, 4))
        mem = psutil.virtual_memory()
        self.lbl_ram_info = tk.Label(c2,
                                     text=f"Total: {mem.total/(1024**3):.1f} GB",
                                     font=("Segoe UI", 8), bg=PANEL_BG, fg=TEXT_FG)
        self.lbl_ram_info.pack(pady=(0, 8))

        # ─ Núcleos ─
        c3 = self._card(parent, 0, 2, f"🔲 Núcleos ({psutil.cpu_count()} lógicos)", ACCENT3)
        nf = tk.Frame(c3, bg=PANEL_BG)
        nf.pack(padx=6, pady=(0, 8), fill="x")
        self.lbl_nucleos = []
        self.bar_nucleos = []
        n    = psutil.cpu_count()
        cols = 2 if n <= 8 else 4
        for i in range(n):
            r = i // cols; cl = i % cols
            sf = tk.Frame(nf, bg=PANEL_BG)
            sf.grid(row=r, column=cl, padx=3, pady=1, sticky="w")
            tk.Label(sf, text=f"C{i}", font=("Segoe UI", 7, "bold"),
                     bg=PANEL_BG, fg=TITLE_FG, width=2).pack(side="left")
            bar = ttk.Progressbar(sf, orient="horizontal", length=70,
                                  mode="determinate", maximum=100)
            bar.pack(side="left", padx=2)
            lbl = tk.Label(sf, text="0%", font=("Segoe UI", 7),
                           bg=PANEL_BG, fg=TEXT_FG, width=4)
            lbl.pack(side="left")
            self.bar_nucleos.append(bar)
            self.lbl_nucleos.append(lbl)

    # ── Fila 1: Gráfica + Log ─────────────────
    def _build_center_row(self, parent):
        parent.rowconfigure(1, weight=1)

        # ─ Gráfica (col 0-1) ─
        gc = self._card(parent, 1, 0, "📈 CPU & RAM en tiempo real",
                        ACCENT1, colspan=2, fill="both", expand=True)
        gc.rowconfigure(1, weight=1)
        self.fig = Figure(figsize=(5, 3), dpi=88, facecolor=PANEL_BG)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor("#FAF7FF")
        self.ax.set_ylim(0, 100)
        self.ax.set_ylabel("%", fontsize=8, color=TEXT_FG)
        self.ax.tick_params(labelsize=7, colors=TEXT_FG)
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.line_cpu, = self.ax.plot([], [], color=GRAPH_CPU, lw=2, label="CPU")
        self.line_ram, = self.ax.plot([], [], color=GRAPH_RAM, lw=2, label="RAM")
        self.ax.legend(loc="upper right", fontsize=8)
        self.fig.tight_layout(pad=1.2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=gc)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ─ Log grande (col 2) ─
        lc = self._card(parent, 1, 2, "📋  Log de ejecución",
                        ACCENT2, fill="both", expand=True)
        lc.rowconfigure(1, weight=1)
        lc.columnconfigure(0, weight=1)

        # Frame interior con scroll
        log_frame = tk.Frame(lc, bg=PANEL_BG)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, font=("Consolas", 8),
                                bg="#F8F5FF", fg=TEXT_FG, relief="flat",
                                state="disabled", wrap="word")
        sb = ttk.Scrollbar(log_frame, orient="vertical",
                           command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        # Botón limpiar log
        tk.Button(lc, text="🗑  Limpiar log", command=self._limpiar_log,
                  bg="#EEE8FF", fg=BTN_FG, relief="flat",
                  font=("Segoe UI", 8), cursor="hand2"
                  ).pack(anchor="e", padx=8, pady=(0, 6))

    # ── Fila 2: imágenes + botones + progreso ─
    def _build_bottom_row(self, parent):
        parent.rowconfigure(2, weight=0)

        # ─ Imágenes + botones (col 0-1) ─
        bc = self._card(parent, 2, 0, None, ACCENT4, colspan=2, fill="x", expand=False, sticky="ew")

        top = tk.Frame(bc, bg=PANEL_BG)
        top.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(top, text="🖼  Procesamiento de Imágenes",
                 font=("Segoe UI", 10, "bold"), bg=PANEL_BG, fg=TITLE_FG
                 ).pack(side="left")

        tk.Button(top, text="📂  Seleccionar carpeta",
                  command=self._seleccionar_carpeta,
                  bg=ACCENT5, fg=BTN_FG, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(16, 8))

        self.lbl_fotos = tk.Label(top, text="Sin carpeta seleccionada",
                                  font=("Segoe UI", 9), bg=PANEL_BG, fg=TEXT_FG)
        self.lbl_fotos.pack(side="left")

        # Botones en columna
        brow = tk.Frame(bc, bg=PANEL_BG)
        brow.pack(fill="x", padx=16, pady=(0, 8))

        def mk_btn(text, value, color):
            def cmd():
                self.metodo_var.set(value)
                for b in [b_seq, b_thr, b_pro]:
                    b.configure(relief="flat")
                btn.configure(relief="sunken")
                self._ejecutar(value)
            btn = tk.Button(brow, text=text, command=cmd,
                            bg=color, fg=BTN_FG, relief="flat",
                            font=("Segoe UI", 10, "bold"), pady=6,
                            cursor="hand2")
            return btn

        b_seq = mk_btn("🔁  Secuencial",   "secuencial", BTN_SEQ)
        b_thr = mk_btn("🧵  Hilos",         "hilos",      BTN_THR)
        b_pro = mk_btn("⚙  Multiprocesos", "procesos",   BTN_PRO)
        b_seq.pack(fill="x", pady=2)
        b_thr.pack(fill="x", pady=2)
        b_pro.pack(fill="x", pady=2)

        # ─ Sistema + progreso (col 2) ─
        sc = self._card(parent, 2, 2, "ℹ  Sistema", ACCENT5, fill="x", expand=False, sticky="ew")
        try:
            import platform
            cpu_model = platform.processor() or platform.machine()
        except:
            cpu_model = "N/A"
        for line in [
            f"Núcleos físicos : {psutil.cpu_count(logical=False)}",
            f"Núcleos lógicos : {psutil.cpu_count(logical=True)}",
            f"RAM total       : {psutil.virtual_memory().total/(1024**3):.2f} GB",
            f"CPU             : {cpu_model[:34]}",
        ]:
            tk.Label(sc, text=line, font=("Consolas", 8),
                     bg=PANEL_BG, fg=TEXT_FG, anchor="w").pack(anchor="w", padx=10, pady=1)

        self.lbl_estado = tk.Label(sc, text="Esperando ejecución...",
                                   font=("Segoe UI", 8), bg=PANEL_BG, fg=TITLE_FG)
        self.lbl_estado.pack(anchor="w", padx=10, pady=(6, 0))
        self.progress = ttk.Progressbar(sc, orient="horizontal",
                                        mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=10, pady=(2, 10))

    # ──────────────────────────────────────────
    # Monitor en segundo plano
    # ──────────────────────────────────────────
    def _start_monitor(self):
        def monitor():
            MAX = 60
            while self.running:
                cpu = psutil.cpu_percent(interval=0.5)
                ram = psutil.virtual_memory().percent
                cores = psutil.cpu_percent(interval=None, percpu=True)

                with self.lock_gui:
                    self.cpu_history.append(cpu)
                    self.ram_history.append(ram)
                    if len(self.cpu_history) > MAX:
                        self.cpu_history.pop(0)
                    if len(self.ram_history) > MAX:
                        self.ram_history.pop(0)

                self.root.after(0, self._actualizar_ui, cpu, ram, cores)
                time.sleep(0.5)

        t = threading.Thread(target=monitor, daemon=True)
        t.start()

    def _actualizar_ui(self, cpu, ram, cores):
        # Labels
        self.lbl_cpu.config(text=f"{cpu:.1f} %")
        self.lbl_ram.config(text=f"{ram:.1f} %")
        self.bar_cpu["value"] = cpu
        self.bar_ram["value"] = ram

        # Color dinámico de CPU
        if cpu < 40:
            self.lbl_cpu.config(fg=GRAPH_CPU)
        elif cpu < 70:
            self.lbl_cpu.config(fg="#D4A020")
        else:
            self.lbl_cpu.config(fg="#D44040")

        # Núcleos
        for i, val in enumerate(cores[:len(self.bar_nucleos)]):
            self.bar_nucleos[i]["value"] = val
            self.lbl_nucleos[i].config(text=f"{val:.0f}%")

        # Gráfica
        with self.lock_gui:
            h_cpu = list(self.cpu_history)
            h_ram = list(self.ram_history)

        xs = list(range(len(h_cpu)))
        self.line_cpu.set_data(xs, h_cpu)
        self.line_ram.set_data(xs, h_ram)
        if xs:
            self.ax.set_xlim(0, max(len(xs), 30))
        self.canvas.draw_idle()

    # ──────────────────────────────────────────
    # Selección de carpeta
    # ──────────────────────────────────────────
    def _seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta con las fotos")
        if not carpeta:
            return
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        todas = [os.path.join(carpeta, f) for f in os.listdir(carpeta)
                 if os.path.splitext(f)[1].lower() in exts]
        todas.sort()
        self.fotos = todas[:30]
        n = len(self.fotos)
        if n == 0:
            messagebox.showwarning("Sin imágenes",
                                   "No se encontraron imágenes en esa carpeta.")
            self.lbl_fotos.config(text="⚠  Sin imágenes válidas")
        else:
            self.lbl_fotos.config(text=f"✅  {n} imagen{'es' if n>1 else ''} cargada{'s' if n>1 else ''}")
            self._log(f"📂 Carpeta: {carpeta}")
            self._log(f"🖼  {n} imagen(es) lista(s) para procesar")

    # ──────────────────────────────────────────
    # Ejecución
    # ──────────────────────────────────────────
    def _ejecutar(self, metodo):
        if self.proceso_activo:
            messagebox.showinfo("Ocupado", "Ya hay una tarea en ejecución. Espera a que termine.")
            return
        if not self.fotos:
            messagebox.showwarning("Sin fotos", "Selecciona primero una carpeta con imágenes.")
            return

        self.proceso_activo = True
        self._log(f"\n{'─'*45}")
        self._log(f"▶  Método: {metodo.upper()}")
        self._log(f"   {len(self.fotos)} imagen(es) a procesar")
        self.progress["value"] = 0
        self.lbl_estado.config(text=f"Procesando con {metodo}...")

        def run():
            # ── Snapshot de recursos ANTES ──────────────
            cpu_antes = psutil.cpu_percent(interval=0.3)
            ram_antes = psutil.virtual_memory().percent
            proc_self = psutil.Process(os.getpid())
            mem_antes_mb = proc_self.memory_info().rss / (1024 * 1024)

            start = time.perf_counter()
            resultados  = []
            tiempos_ind = []   # (nombre, t_seg, cpu_snap, ram_snap)

            if metodo == "secuencial":
                for idx, foto in enumerate(self.fotos):
                    nombre = os.path.basename(foto)
                    cpu_s = psutil.cpu_percent(interval=None)
                    ram_s = psutil.virtual_memory().percent
                    t0 = time.perf_counter()
                    r  = convertir_gris(foto)
                    t1 = time.perf_counter() - t0
                    tiempos_ind.append((nombre, t1, cpu_s, ram_s))
                    resultados.append((nombre, t1, r))
                    pct = int((idx + 1) / len(self.fotos) * 100)
                    msg = (f"  [{idx+1:02d}] {nombre:<28} "
                           f"{t1*1000:6.1f} ms  "
                           f"CPU {cpu_s:4.1f}%  RAM {ram_s:4.1f}%")
                    self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                    self._log(msg)

            elif metodo == "hilos":
                total   = len(self.fotos)
                counter = [0]
                lock    = threading.Lock()

                def _worker(foto):
                    nombre = os.path.basename(foto)
                    cpu_s = psutil.cpu_percent(interval=None)
                    ram_s = psutil.virtual_memory().percent
                    t0 = time.perf_counter()
                    with self.semaforo:
                        r = convertir_gris(foto)
                    t1 = time.perf_counter() - t0
                    with lock:
                        tiempos_ind.append((nombre, t1, cpu_s, ram_s))
                        resultados.append((nombre, t1, r))
                        counter[0] += 1
                        idx = counter[0]
                        pct = int(idx / total * 100)
                        msg = (f"  [{idx:02d}] {nombre:<28} "
                               f"{t1*1000:6.1f} ms  "
                               f"CPU {cpu_s:4.1f}%  RAM {ram_s:4.1f}%")
                        self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                        self._log(msg)

                hilos = [threading.Thread(target=_worker, args=(f,)) for f in self.fotos]
                for h in hilos: h.start()
                for h in hilos: h.join()

            elif metodo == "procesos":
                import subprocess, sys, json, tempfile

                n_workers = min(multiprocessing.cpu_count(), len(self.fotos))
                counter_p = [0]
                lock_p    = threading.Lock()

                worker_script = r"""
import sys, json, time, os
from PIL import Image

def convertir(path):
    try:
        img = Image.open(path).convert("L")
        base, ext = os.path.splitext(path)
        out = base + "_gray" + ext
        img.save(out)
        return out
    except Exception as e:
        return f"ERROR: {e}"

data = json.loads(sys.argv[1])
t0 = time.perf_counter()
r  = convertir(data["path"])
t1 = time.perf_counter() - t0
print(json.dumps({"nombre": os.path.basename(data["path"]), "t": t1, "r": r}))
"""
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                                  delete=False, encoding="utf-8")
                tmp.write(worker_script)
                tmp.close()
                script_path = tmp.name
                semaforo_proc = threading.Semaphore(n_workers)

                def _run_proc(foto):
                    nombre = os.path.basename(foto)
                    cpu_s = psutil.cpu_percent(interval=None)
                    ram_s = psutil.virtual_memory().percent
                    with semaforo_proc:
                        try:
                            arg = json.dumps({"path": foto})
                            proc = subprocess.run(
                                [sys.executable, script_path, arg],
                                capture_output=True, text=True, timeout=30
                            )
                            data = json.loads(proc.stdout.strip())
                            nombre = data["nombre"]
                            t1     = data["t"]
                            r      = data["r"]
                        except Exception as e:
                            t1 = 0.0
                            r  = f"ERROR: {e}"
                    with lock_p:
                        tiempos_ind.append((nombre, t1, cpu_s, ram_s))
                        resultados.append((nombre, t1, r))
                        counter_p[0] += 1
                        idx_p = counter_p[0]
                        pct   = int(idx_p / len(self.fotos) * 100)
                        msg   = (f"  [{idx_p:02d}] {nombre:<28} "
                                 f"{t1*1000:6.1f} ms  "
                                 f"CPU {cpu_s:4.1f}%  RAM {ram_s:4.1f}%")
                        self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                        self._log(msg)

                hilos_proc = [threading.Thread(target=_run_proc, args=(f,))
                              for f in self.fotos]
                for h in hilos_proc: h.start()
                for h in hilos_proc: h.join()
                try:
                    os.unlink(script_path)
                except:
                    pass

            # ── Snapshot de recursos DESPUÉS ────────────
            elapsed      = time.perf_counter() - start
            cpu_despues  = psutil.cpu_percent(interval=0.3)
            ram_despues  = psutil.virtual_memory().percent
            mem_desp_mb  = proc_self.memory_info().rss / (1024 * 1024)
            cpu_delta    = cpu_despues - cpu_antes
            ram_delta    = ram_despues - ram_antes
            mem_delta    = mem_desp_mb - mem_antes_mb

            ok  = sum(1 for _, _, r in resultados if not str(r).startswith("ERROR"))
            err = len(resultados) - ok

            solo_tiempos = [t for _, t, _, _ in tiempos_ind]
            cpu_prom_uso = sum(c for _, _, c, _ in tiempos_ind) / max(len(tiempos_ind), 1)
            ram_prom_uso = sum(r for _, _, _, r in tiempos_ind) / max(len(tiempos_ind), 1)

            # Guardar para tabla comparativa
            self.historial_comparativo[metodo] = {
                "elapsed":      elapsed,
                "t_min":        min(solo_tiempos) if solo_tiempos else 0,
                "t_max":        max(solo_tiempos) if solo_tiempos else 0,
                "t_prom":       sum(solo_tiempos) / max(len(solo_tiempos), 1),
                "cpu_antes":    cpu_antes,
                "cpu_despues":  cpu_despues,
                "cpu_delta":    cpu_delta,
                "cpu_prom":     cpu_prom_uso,
                "ram_antes":    ram_antes,
                "ram_despues":  ram_despues,
                "ram_delta":    ram_delta,
                "ram_prom":     ram_prom_uso,
                "mem_delta_mb": mem_delta,
                "ok":           ok,
                "err":          err,
            }

            self.root.after(0, lambda: self._finalizar(
                metodo, elapsed, ok, err, solo_tiempos,
                cpu_antes, cpu_despues, cpu_delta, cpu_prom_uso,
                ram_antes, ram_despues, ram_delta, ram_prom_uso, mem_delta
            ))

        threading.Thread(target=run, daemon=True).start()

    def _finalizar(self, metodo, elapsed, ok, err, tiempos,
                   cpu_antes, cpu_despues, cpu_delta, cpu_prom,
                   ram_antes, ram_despues, ram_delta, ram_prom, mem_delta):
        self.proceso_activo = False
        self.progress["value"] = 100
        self.lbl_estado.config(text=f"✅ {metodo.upper()} — {elapsed:.3f} s  |  OK: {ok}  Errores: {err}")

        sep = "─" * 52
        self._log(f"\n{sep}")
        self._log(f"  📊 RESUMEN — {metodo.upper()}")
        self._log(sep)

        # Tiempos
        if tiempos:
            t_min  = min(tiempos)
            t_max  = max(tiempos)
            t_prom = sum(tiempos) / len(tiempos)
            self._log(f"  ⏱  Tiempo total      : {elapsed*1000:8.1f} ms")
            self._log(f"  📉 Imagen más rápida : {t_min*1000:8.1f} ms")
            self._log(f"  📈 Imagen más lenta  : {t_max*1000:8.1f} ms")
            self._log(f"  📐 Promedio/imagen   : {t_prom*1000:8.1f} ms")

        # CPU
        signo_cpu = "+" if cpu_delta >= 0 else ""
        self._log(f"  ⚡ CPU antes         : {cpu_antes:7.1f} %")
        self._log(f"  ⚡ CPU después       : {cpu_despues:7.1f} %")
        self._log(f"  ⚡ Δ CPU (impacto)   : {signo_cpu}{cpu_delta:6.1f} %")
        self._log(f"  ⚡ CPU prom. durante : {cpu_prom:7.1f} %")

        # RAM
        signo_ram = "+" if ram_delta >= 0 else ""
        self._log(f"  🧠 RAM antes         : {ram_antes:7.1f} %")
        self._log(f"  🧠 RAM después       : {ram_despues:7.1f} %")
        self._log(f"  🧠 Δ RAM (impacto)   : {signo_ram}{ram_delta:6.1f} %")
        self._log(f"  🧠 RAM prom. durante : {ram_prom:7.1f} %")
        signo_mem = "+" if mem_delta >= 0 else ""
        self._log(f"  💾 Δ Memoria proceso : {signo_mem}{mem_delta:6.1f} MB")

        self._log(f"  ✅ Convertidas: {ok}   ❌ Errores: {err}")
        self._log(sep)

        notas = {
            "secuencial": "ℹ  Secuencial: una imagen a la vez, sin overhead\n   de sincronización ni paralelismo.",
            "hilos":      "ℹ  Hilos: concurrente con Semaphore. Pillow libera\n   el GIL, por eso hay ganancia real en I/O.",
            "procesos":   "ℹ  Multiprocesos: subprocesos reales, paralelismo\n   verdadero. Overhead de arranque visible.",
        }
        self._log(notas.get(metodo, ""))
        self._log("")

        # ── Tabla comparativa si ya hay 2+ métodos ──────────
        if len(self.historial_comparativo) >= 2:
            self._mostrar_tabla_comparativa()

    def _mostrar_tabla_comparativa(self):
        h = self.historial_comparativo
        metodos = ["secuencial", "hilos", "procesos"]
        presentes = [m for m in metodos if m in h]

        sep  = "═" * 62
        sep2 = "─" * 62
        self._log(f"\n{sep}")
        self._log(f"  🏆  TABLA COMPARATIVA DE MÉTODOS")
        self._log(sep)

        # Encabezado
        col = 18
        header = f"  {'Métrica':<22}"
        for m in presentes:
            header += f"  {m.upper():>{col}}"
        self._log(header)
        self._log(sep2)

        def fila(etiqueta, fn, fmt="{:.1f}"):
            linea = f"  {etiqueta:<22}"
            for m in presentes:
                try:
                    val = fn(h[m])
                    linea += f"  {fmt.format(val):>{col}}"
                except:
                    linea += f"  {'N/A':>{col}}"
            return linea

        self._log(fila("⏱ Tiempo total (ms)",  lambda d: d["elapsed"]*1000))
        self._log(fila("📉 Más rápida (ms)",    lambda d: d["t_min"]*1000))
        self._log(fila("📈 Más lenta (ms)",     lambda d: d["t_max"]*1000))
        self._log(fila("📐 Promedio/img (ms)",  lambda d: d["t_prom"]*1000))
        self._log(sep2)
        self._log(fila("⚡ CPU antes (%)",      lambda d: d["cpu_antes"]))
        self._log(fila("⚡ CPU después (%)",    lambda d: d["cpu_despues"]))
        self._log(fila("⚡ Δ CPU impacto (%)",  lambda d: d["cpu_delta"], fmt="{:+.1f}"))
        self._log(fila("⚡ CPU prom. (%)",      lambda d: d["cpu_prom"]))
        self._log(sep2)
        self._log(fila("🧠 RAM antes (%)",      lambda d: d["ram_antes"]))
        self._log(fila("🧠 RAM después (%)",    lambda d: d["ram_despues"]))
        self._log(fila("🧠 Δ RAM impacto (%)",  lambda d: d["ram_delta"], fmt="{:+.1f}"))
        self._log(fila("🧠 RAM prom. (%)",      lambda d: d["ram_prom"]))
        self._log(fila("💾 Δ Mem proceso (MB)", lambda d: d["mem_delta_mb"], fmt="{:+.1f}"))
        self._log(sep2)
        self._log(fila("✅ OK",                 lambda d: d["ok"],  fmt="{:.0f}"))
        self._log(fila("❌ Errores",            lambda d: d["err"], fmt="{:.0f}"))
        self._log(sep)

        # Ganador por tiempo
        if len(presentes) > 1:
            ganador = min(presentes, key=lambda m: h[m]["elapsed"])
            self._log(f"  🥇 Más rápido: {ganador.upper()}"
                      f"  ({h[ganador]['elapsed']*1000:.1f} ms total)")
        self._log(sep)
        self._log("")

    def _limpiar_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _log(self, msg):
        def _write():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _write)

    # ──────────────────────────────────────────
    # Cierre
    # ──────────────────────────────────────────
    def on_close(self):
        self.running = False
        self.root.destroy()


# ──────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app  = MonitorApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()