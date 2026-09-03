import { contextBridge, ipcRenderer } from "electron";
import type { DesktopApi, TaskEvent } from "@aida/contracts";

const api: DesktopApi = {
  sidecarRequest: (path, init) => ipcRenderer.invoke("sidecar:request", path, init),
  selectDataFile: () => ipcRenderer.invoke("file:select-data"),
  selectProjectDirectory: () => ipcRenderer.invoke("file:select-project"),
  saveExport: (name, content, encoding) => ipcRenderer.invoke("file:save-export", name, content, encoding),
  setSecret: (key, value) => ipcRenderer.invoke("secret:set", key, value),
  getSecret: (key) => ipcRenderer.invoke("secret:get", key),
  deleteSecret: (key) => ipcRenderer.invoke("secret:delete", key),
  subscribeTask: (taskId, listener) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: TaskEvent) => { if (payload.taskId === taskId) listener(payload); };
    ipcRenderer.on("task:event", handler);
    return () => ipcRenderer.removeListener("task:event", handler);
  }
};

contextBridge.exposeInMainWorld("aida", api);

