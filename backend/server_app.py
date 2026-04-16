import serial
import serial.tools.list_ports
import threading
import socket
import json
import time
import os
import csv
import struct
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# Cria o diretório de dados se não existir
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

class BackendServer:
    def __init__(self, root):
        self.root = root
        self.root.title("Napro Backend Server")
        self.root.geometry("850x650")
        
        self.running = False
        self.clients = []
        self.csv_lock = threading.Lock()
        
        self.csv_handle = None
        self.csv_writer = None
        self.pol_handle = None
        self.pol_writer = None
        self.buffer_eqp = bytearray()
        self.sv_socket = None
        
        self.data_queue = queue.Queue()

        self._build_ui()
        self.poll_queue()

    def _build_ui(self):
        f = tk.Frame(self.root, padx=10, pady=10)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="🔧 Módulo de Comunicação NAPRO", font=("Arial", 12, "bold")).pack(pady=5)

        f_top = tk.Frame(f)
        f_top.pack(fill="x", pady=5)

        f_ports = tk.LabelFrame(f_top, text="Configuração das Portas e Servidor", padx=10, pady=10)
        f_ports.pack(side="left", fill="x", expand=True, padx=(0, 5))

        tk.Label(f_ports, text="Porta Equipamento (Real):").grid(row=0, column=0, sticky="w")
        self.cb_real = ttk.Combobox(f_ports, values=self.get_ports(), width=12)
        self.cb_real.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(f_ports, text="Porta Software (VCOM):").grid(row=1, column=0, sticky="w")
        self.cb_virt = ttk.Combobox(f_ports, values=self.get_ports(), width=12)
        self.cb_virt.grid(row=1, column=1, padx=5, pady=5)

        f_controls = tk.Frame(f_top)
        f_controls.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.btn_start = tk.Button(f_controls, text="▶ INICIAR SERVIDOR", command=self.toggle_server, bg="#28a745", fg="white", font=("Arial", 10, "bold"), pady=5)
        self.btn_start.pack(fill="x", pady=(5, 0))

        self.btn_reset = tk.Button(f_controls, text="♻️ NOVO CICLO GLOBAL", command=self.trigger_global_reset, bg="#17a2b8", fg="white", font=("Arial", 9, "bold"), pady=2)
        self.btn_reset.pack(fill="x", pady=(2, 0))

        self.lbl_status = tk.Label(f_controls, text="Servidor Parado", fg="red", font=("Arial", 10))
        self.lbl_status.pack(pady=2)

        self.lbl_clients = tk.Label(f_controls, text="Clientes Conectados: 0", font=("Arial", 10))
        self.lbl_clients.pack()

        # Label State
        self.lbl_eqp = tk.Label(f, text="STATUS EQUIPAMENTO: [ DESCONHECIDO ]", font=("Consolas", 12, "bold"), fg="#ff7675")
        self.lbl_eqp.pack(pady=5)

        # TREEVIEW RAW
        f_tree = tk.LabelFrame(f, text=" Log de Comunicação Serial Bruta ", padx=5, pady=5)
        f_tree.pack(fill="both", expand=True)

        columns = ("Time", "Direction", "Data (Hex)", "Notes")
        self.tree_raw = ttk.Treeview(f_tree, columns=columns, show="headings", selectmode="extended")
        
        self.tree_raw.heading("Time", text="Hora")
        self.tree_raw.column("Time", width=100, stretch=False, anchor="center")
        self.tree_raw.heading("Direction", text="Direção")
        self.tree_raw.column("Direction", width=120, stretch=False, anchor="center")
        self.tree_raw.heading("Data (Hex)", text="Dados (Hex)")
        self.tree_raw.column("Data (Hex)", width=350, stretch=True)
        self.tree_raw.heading("Notes", text="Status / Notas")
        self.tree_raw.column("Notes", width=180, stretch=False)
        
        self.tree_raw.tag_configure("SOF_TO_EQP", foreground="#005500", background="#e8f5e9")
        self.tree_raw.tag_configure("EQP_TO_SOF", foreground="#0000AA", background="#e3f2fd")

        scrollbar = ttk.Scrollbar(f_tree, orient="vertical", command=self.tree_raw.yview)
        self.tree_raw.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree_raw.pack(side="left", fill="both", expand=True)

    def poll_queue(self):
        try:
            items_processed = 0
            last_item = None
            
            for _ in range(500):
                item = self.data_queue.get_nowait()
                if item[0] == "RAW":
                    _, timestamp, direction, hex_data, note = item
                    
                    if note:
                        self.lbl_eqp.config(text=f"STATUS EQUIPAMENTO: [ {note} ]", fg="#0984e3")
                        
                    dir_label = "SOF -> EQP" if direction == "SOF_TO_EQP" else "EQP -> SOF"
                    last_item = self.tree_raw.insert("", tk.END, values=(timestamp, dir_label, hex_data, note), tags=(direction,))
                    items_processed += 1
            
            if items_processed > 0:
                if last_item:
                    self.tree_raw.see(last_item)
                
                ch = self.tree_raw.get_children()
                if len(ch) > 2000:
                    self.tree_raw.delete(*ch[:-2000])
                    
        except queue.Empty: pass
        self.root.after(50, self.poll_queue)

    def get_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def init_csv(self):
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        with self.csv_lock:
            self.csv_handle = open(os.path.join(DATA_DIR, f"serial_raw_log_{ts}.csv"), "w", newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.csv_handle)
            self.csv_writer.writerow(["dateTime", "Direção", "Hex", "ASCII", "Nota"])
            self.csv_handle.flush()

            self.pol_handle = open(os.path.join(DATA_DIR, f"pollutants_{ts}.csv"), "w", newline='', encoding='utf-8')
            self.pol_writer = csv.writer(self.pol_handle, delimiter=';')
            self.pol_writer.writerow(["dateTime", "CO_%", "CO2_%", "HC_ppm", "O2_%", "NOx_ppm", "RPM", "Temp_C"])

            self.pol_handle.flush()

    def close_csv(self):
        with self.csv_lock:
            if self.csv_handle:
                self.csv_handle.close()
                self.csv_handle = None
                self.csv_writer = None
            if self.pol_handle:
                self.pol_handle.close()
                self.pol_handle = None
                self.pol_writer = None

    def execute_reset_cycle(self):
        # Reset server side files and cache
        self.close_csv()
        self.init_csv()
        self.tree_raw.delete(*self.tree_raw.get_children())

    def trigger_global_reset(self):
        if not self.running:
            return
        self.execute_reset_cycle()
        # Broadcast the signal to clients too
        self.broadcast({"type": "CMD", "action": "NEW_SESSION"})

    def client_listen(self, client):
        client.settimeout(None)
        buffer = ""
        while self.running:
            try:
                data = client.recv(1024)
                if not data: break
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if '"action": "NEW_SESSION"' in line:
                        # Server received reset command from ANY client
                        self.root.after(0, self.trigger_global_reset)
            except Exception: 
                break
        
        if client in self.clients: self.clients.remove(client)
        self.root.after(0, self.update_client_count)

    def socket_server_thread(self):
        self.sv_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sv_socket.bind(("0.0.0.0", 9999))
        self.sv_socket.listen(5)
        self.sv_socket.settimeout(1.0)
        
        while self.running:
            try:
                client, addr = self.sv_socket.accept()
                self.clients.append(client)
                self.update_client_count()
                threading.Thread(target=self.client_listen, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running: print(f"Erro no Socket Server: {e}")
                
        try:
            self.sv_socket.close()
        except: pass

    def update_client_count(self):
        # Limpa os inativos primeiro (lazy)
        self.root.after(0, self.lbl_clients.config, {"text": f"Clientes Conectados: {len(self.clients)}"})

    def broadcast(self, payload):
        dead_clients = []
        msg = json.dumps(payload) + "\n"
        encoded = msg.encode('utf-8')
        
        for c in self.clients:
            try:
                c.sendall(encoded)
            except Exception as e:
                dead_clients.append(c)
                
        for c in dead_clients:
            if c in self.clients: self.clients.remove(c)
            try: c.close()
            except: pass
        
        if dead_clients:
            self.update_client_count()

    def extract_packet_data(self, pkt, timestamp):
        try:
            hc_raw = struct.unpack('<H', pkt[6:8])[0]
            co_raw = struct.unpack('<H', pkt[8:10])[0]
            co2_raw = struct.unpack('<H', pkt[10:12])[0]
            o2_raw = struct.unpack('<H', pkt[12:14])[0]
            nox_raw = struct.unpack('<H', pkt[14:16])[0]
            rpm_raw = struct.unpack('<H', pkt[16:18])[0]
            temp_raw = struct.unpack('<H', pkt[18:20])[0]

            co = co_raw / 100.0 if co_raw < 10000 else None
            hc = hc_raw if hc_raw < 10000 else None
            co2 = co2_raw / 10.0 if co2_raw < 10000 else None
            o2 = o2_raw / 100.0 if o2_raw < 10000 else None
            nox = nox_raw if nox_raw < 10000 else None
            rpm = rpm_raw if rpm_raw < 10000 else None
            temp = temp_raw / 10.0 if temp_raw < 10000 else None
            
            if co is not None and hc is not None:
                return {
                    "Time": timestamp, "CO": co, "CO2": co2, "HC": hc, 
                    "O2": o2, "NOx": nox, "RPM": rpm, "Temp": temp
                }
        except Exception as e:
            pass
        return None

    def decode_state(self, hex_data):
        if "04 00 00 00 04 00" in hex_data: return "AQUECIMENTO / AGUARDE"
        elif "00 03 00 01 00 00 00 20 00 2C 00" in hex_data or "00 03 00 01 00 00 00 34 00 40 00" in hex_data: return "REALIZANDO ZERO"
        elif "02 00 02 00 00 00 07 00" in hex_data or "00 02 00 00 00 07 00" in hex_data: return "CALIBRANDO"
        elif "08 00 03 00 01 00 00 00 10 00 1C 00" in hex_data: return "AGUARDANDO MEDIÇÃO"
        return ""

    def bridge(self, src, dest, dir):
        while self.running:
            try:
                # Com timeout=0.05, read(1024) bloqueia por ate 50ms pegando o buffer todo
                d = src.read(1024) 
                
                if d:
                    # Envia pra outra porta
                    try:
                        dest.write(d)
                    except serial.SerialTimeoutException:
                        pass # previne deadlock no write se o outro lado congelou (ex: cabo solto ou simulador lento)
                    
                    now = datetime.now()
                    timestamp = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    csv_stamp = now.strftime('%Y-%m-%dT%H:%M:%S')
                    hex_data = ' '.join([f'{b:02X}' for b in d])
                    note = self.decode_state(hex_data)

                    with self.csv_lock:
                        if self.csv_writer:
                            self.csv_writer.writerow([csv_stamp, dir, hex_data, "", note])
                            self.csv_handle.flush()

                    decoded_pkts = []
                    
                    if dir == "EQP_TO_SOF":
                        self.buffer_eqp.extend(d)
                        while b'\x03\x06\x14' in self.buffer_eqp:
                            idx = self.buffer_eqp.find(b'\x03\x06\x14')
                            if idx > 0:
                                self.buffer_eqp = self.buffer_eqp[idx:]
                                idx = 0
                            
                            if len(self.buffer_eqp) >= 46:
                                pkt = self.buffer_eqp[:46]
                                rec = self.extract_packet_data(pkt, timestamp)
                                if rec:
                                    rec["CSV_Time"] = csv_stamp
                                    decoded_pkts.append(rec)
                                    with self.csv_lock:
                                        if self.pol_writer:
                                            self.pol_writer.writerow([
                                                rec["CSV_Time"],
                                                str(rec["CO"]),
                                                str(rec["CO2"]),
                                                str(rec["HC"]),
                                                str(rec["O2"]),
                                                str(rec["NOx"]),
                                                str(rec["RPM"]),
                                                str(rec["Temp"])
                                            ])
                                            self.pol_handle.flush()
                                self.buffer_eqp = self.buffer_eqp[46:]
                            else:
                                break

                    if decoded_pkts or note:
                        self.broadcast({
                            "type": "POLLUTANTS",
                            "note": note,
                            "packets": decoded_pkts
                        })
                        
                    self.data_queue.put(("RAW", timestamp, dir, hex_data, note))

            except Exception as e:
                # O Erro de bridge (desconexão hardware) quebra o loop e notifica parada
                print(f"Bridge {dir} break: {e}")
                self.root.after(0, self.stop_server_on_error, str(e))
                break

    def stop_server_on_error(self, err_msg):
        if self.running:
            self.toggle_server()
            messagebox.showerror("Conexão Perdida", f"O Hardware foi desconectado ou ocorreu um erro grave.\nDetalhes: {err_msg}")

    def toggle_server(self):
        if not self.running:
            if not self.cb_real.get() or not self.cb_virt.get():
                messagebox.showerror("Erro", "Selecione ambas as portas.")
                return
            try:
                self.ser_real = serial.Serial(self.cb_real.get(), 9600, timeout=0.05, write_timeout=0.1)
                self.ser_virt = serial.Serial(self.cb_virt.get(), 9600, timeout=0.05, write_timeout=0.1)
                
                self.init_csv()
                self.running = True
                
                self.tree_raw.delete(*self.tree_raw.get_children())
                self.lbl_eqp.config(text="STATUS EQUIPAMENTO: [ CONECTADO / AGUARDANDO DADOS ]", fg="#00b894")
                
                threading.Thread(target=self.socket_server_thread, daemon=True).start()
                threading.Thread(target=self.bridge, args=(self.ser_virt, self.ser_real, "SOF_TO_EQP"), daemon=True).start()
                threading.Thread(target=self.bridge, args=(self.ser_real, self.ser_virt, "EQP_TO_SOF"), daemon=True).start()
                
                self.btn_start.config(text="■ DERRUBAR SERVIDOR", bg="#dc3545")
                self.lbl_status.config(text="● Servidor Rodando (Porta TCP 9999) & Ponte Serial Ativa", fg="green")
                self.cb_real.config(state="disabled")
                self.cb_virt.config(state="disabled")

            except Exception as e: 
                messagebox.showerror("Erro", str(e))
        else:
            self.running = False
            self.close_csv()
            if hasattr(self, 'ser_real') and self.ser_real.is_open: self.ser_real.close()
            if hasattr(self, 'ser_virt') and self.ser_virt.is_open: self.ser_virt.close()
            
            # Derruba as conexões limpas ativas para os clients
            for c in self.clients:
                try: c.close()
                except: pass
            self.clients.clear()
            self.update_client_count()

            self.btn_start.config(text="▶ INICIAR SERVIDOR", bg="#28a745")
            self.lbl_status.config(text="Servidor Parado", fg="red")
            self.lbl_eqp.config(text="STATUS EQUIPAMENTO: [ DESCONHECIDO ]", fg="#ff7675")
            self.cb_real.config(state="normal")
            self.cb_virt.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = BackendServer(root)
    root.mainloop()
