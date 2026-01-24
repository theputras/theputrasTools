
window.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("uuidInput");
    const table = document.getElementById("uuidTable");
    let dataList = JSON.parse(localStorage.getItem("rfidData")) || [];
    const warning = document.getElementById("warning");
    const detectionBadge = document.getElementById("detectionBadge");
    const detectionIcon = document.getElementById("detectionIcon");
    const detectionText = document.getElementById("detectionText");
    
    // Checkbox mode state
    let isCheckboxMode = false;
    let selectedItems = new Set();
    
    // RFID Serial Port state
    let port = null;
    let reader = null;
    let isReading = false;
    
    // Fokus otomatis saat halaman dibuka
    window.onload = function () {
        input.focus();
        renderTable();
        checkSerialSupport();
      };

// Real-time detection saat user mengetik
input.addEventListener("input", function (e) {
    const value = e.target.value.trim();
    
    if (!value) {
        detectionBadge.classList.add("hidden");
        return;
    }
    
    const len = value.length;
    detectionBadge.classList.remove("hidden");
    
    if (len === 8) {
        // UUID detected
        detectionBadge.querySelector("div").className = "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold transition-all bg-blue-500/20 border border-blue-400/40 text-blue-300";
        detectionIcon.className = "fas fa-fingerprint";
        detectionText.textContent = "UUID";
    } else if (len === 11) {
        // NIM detected
        detectionBadge.querySelector("div").className = "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold transition-all bg-green-500/20 border border-green-400/40 text-green-300";
        detectionIcon.className = "fas fa-id-card";
        detectionText.textContent = "NIM";
    } else {
        // Invalid length
        detectionBadge.querySelector("div").className = "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold transition-all bg-yellow-500/20 border border-yellow-400/40 text-yellow-300";
        detectionIcon.className = "fas fa-question-circle";
        detectionText.textContent = `${len} digit`;
    }
});

// Tambah data dari input dengan AUTO-DETECT
input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
        const value = input.value.trim();
        if (!value) return;

        // AUTO-DETECT berdasarkan panjang
        let mode, maxLen;
        if (value.length === 8) {
            mode = "uuid";
            maxLen = 8;
        } else if (value.length === 11) {
            mode = "nim";
            maxLen = 11;
        } else {
            alertBox(`❌ Panjang tidak valid! UUID (8 digit) atau NIM (11 digit)`, "warning");
            input.value = "";
            detectionBadge.classList.add("hidden");
            return;
        }

        // Cek duplikat
        const exists = dataList.find((item) => item[mode] === value);
        if (exists) {
            alertBox(`⚠️ ${mode.toUpperCase()} "${value}" sudah ada!`, "warning");
            
            // Broadcast duplicate warning to public screen
            fetch('/api/sskm/duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: mode, value: value })
            }).catch(err => console.error('Error sending duplicate warning:', err));
            
        } else {
            const time = new Date().toLocaleString();
            const newData = {
              uuid: mode === "uuid" ? value : "",
              nim: mode === "nim" ? value : "",
              time
            };
            dataList.push(newData);
            saveData();
            renderTable();
            alertBox(`✅ ${mode.toUpperCase()} berhasil disimpan!`, "success");
        }
        input.value = "";
        detectionBadge.classList.add("hidden");
    }
  });
  
  // Show Download Modal
  function saveToExcel() {
    const downloadModal = document.getElementById("downloadModal");
    downloadModal.classList.remove("hidden");
  }

  // Download handler
  document.getElementById("downloadSingle")?.addEventListener("click", () => {
    downloadSingleExcel();
    document.getElementById("downloadModal").classList.add("hidden");
  });

  document.getElementById("downloadSeparate")?.addEventListener("click", () => {
    downloadSeparateZip();
    document.getElementById("downloadModal").classList.add("hidden");
  });

  document.getElementById("cancelDownload")?.addEventListener("click", () => {
    document.getElementById("downloadModal").classList.add("hidden");
  });

  // Single Excel with 2 sheets
  function downloadSingleExcel() {
    const uuidData = [["No", "UUID", "Waktu"]];
    const nimData = [["No", "NIM", "Waktu"]];
    
    dataList.forEach((item, i) => {
      if (item.uuid) {
        uuidData.push([i + 1, item.uuid, item.time]);
      } 
      if (item.nim) {
        nimData.push([i + 1, item.nim, item.time]);
      }
    });

    const uuidWorksheet = XLSX.utils.aoa_to_sheet(uuidData);
    const nimWorksheet = XLSX.utils.aoa_to_sheet(nimData);

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, uuidWorksheet, "UUID");
    XLSX.utils.book_append_sheet(workbook, nimWorksheet, "NIM");

    const currentDate = new Date().toISOString().slice(0, 10);
    const filename = `Recap_Tapping_SSKM_${currentDate}.xlsx`;
    XLSX.writeFile(workbook, filename);
    
    alertBox("✅ File Excel berhasil diunduh!", "success");
  }

  // Separate files + ZIP
  function downloadSeparateZip() {
    if (typeof JSZip === 'undefined') {
      alertBox("❌ JSZip library tidak tersedia!", "error");
      return;
    }

    const zip = new JSZip();
    const currentDate = new Date().toISOString().slice(0, 10);

    // Create UUID Excel
    const uuidData = [["No", "UUID", "Waktu"]];
    dataList.forEach((item, i) => {
      if (item.uuid) {
        uuidData.push([i + 1, item.uuid, item.time]);
      }
    });
    const uuidWorksheet = XLSX.utils.aoa_to_sheet(uuidData);
    const uuidWorkbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(uuidWorkbook, uuidWorksheet, "UUID");
    const uuidFile = XLSX.write(uuidWorkbook, { type: 'array', bookType: 'xlsx' });
    zip.file(`UUID_${currentDate}.xlsx`, uuidFile);

    // Create NIM Excel
    const nimData = [["No", "NIM", "Waktu"]];
    dataList.forEach((item, i) => {
      if (item.nim) {
        nimData.push([i + 1, item.nim, item.time]);
      }
    });
    const nimWorksheet = XLSX.utils.aoa_to_sheet(nimData);
    const nimWorkbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(nimWorkbook, nimWorksheet, "NIM");
    const nimFile = XLSX.write(nimWorkbook, { type: 'array', bookType: 'xlsx' });
    zip.file(`NIM_${currentDate}.xlsx`, nimFile);

    // Generate ZIP
    zip.generateAsync({ type: 'blob' }).then(function(content) {
      const url = URL.createObjectURL(content);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Recap_Tapping_SSKM_${currentDate}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      alertBox("✅ File ZIP berhasil diunduh!", "success");
    });
  }

  
  
  // Render data ke tabel
  function renderTable() {
    table.innerHTML = "";
    dataList.forEach((item, index) => {
      const row = table.insertRow();
      
      // First column: No or Checkbox
      const firstCell = row.insertCell(0);
      if (isCheckboxMode) {
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "w-4 h-4 cursor-pointer";
        checkbox.checked = selectedItems.has(index);
        checkbox.onchange = (e) => {
          if (e.target.checked) {
            selectedItems.add(index);
          } else {
            selectedItems.delete(index);
          }
          updateDeleteButton();
          updateSelectAllCheckbox();
        };
        firstCell.appendChild(checkbox);
      } else {
        firstCell.innerText = index + 1;
      }
      
      row.insertCell(1).innerText = item.uuid || "-";
      row.insertCell(2).innerText = item.nim || "-";
      row.insertCell(3).innerText = item.time;
  
      const aksiCell = row.insertCell(4);
      const delBtn = document.createElement("button");
      delBtn.innerText = "❌";
      delBtn.className = "delete-btn hover:scale-110 transition";
      delBtn.onclick = () => {
        alertBox("Yakin mau hapus data ini?", "confirm", (yes) => {
          if (yes) {
            dataList.splice(index, 1);
            saveData();
            selectedItems.clear();
            renderTable();
            updateDeleteButton();
          }
        });
      };
      aksiCell.appendChild(delBtn);
    });
    
    updateDeleteButton();
  }
  
  // Simpan ke localStorage
  function saveData() {
    localStorage.setItem("rfidData", JSON.stringify(dataList));
    syncToServer(); // Sync to server for real-time counting
  }
  
  // Sync data to server for SSE
  function syncToServer() {
    fetch('/api/sskm/sync', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        rfidData: dataList
      })
    }).catch(err => {
      console.error('Failed to sync to server:', err);
    });
  }
  
  // Load dari localStorage
  function loadDataToTable() {
    renderTable();
  }
  
  // Hapus semua data
  function clearAllData() {
    alertBox("Yakin mau hapus semua data?", "confirm", (yes) => {
        if (yes) {
               dataList = [];
      saveData();
      renderTable();
    saveData();
    renderTable();
        } else {
          // batal
          alertBox("❌ Dibatalkan", "info");
        }
      });
    
    // if (confirm("Yakin ingin menghapus semua data?")) {
    //   dataList = [];
    //   saveData();
    //   renderTable();
    // }
  }
  
  // Toggle Checkbox Mode
  function toggleCheckboxMode() {
    isCheckboxMode = !isCheckboxMode;
    const headerNoText = document.getElementById("headerNoText");
    
    if (isCheckboxMode) {
      // Switch to checkbox mode - show select all checkbox
      selectedItems.clear();
      headerNoText.innerHTML = `<input type="checkbox" id="selectAllCheckbox" class="w-4 h-4 cursor-pointer" onchange="toggleSelectAll(this.checked)">`;
    } else {
      // Switch back to normal mode
      selectedItems.clear();
      headerNoText.textContent = "No";
    }
    
    renderTable();
  }
  
  // Select/Deselect All
  function toggleSelectAll(checked) {
    if (checked) {
      dataList.forEach((_, index) => selectedItems.add(index));
    } else {
      selectedItems.clear();
    }
    renderTable();
  }
  
  // Update select all checkbox state
  function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById("selectAllCheckbox");
    if (selectAllCheckbox && dataList.length > 0) {
      selectAllCheckbox.checked = selectedItems.size === dataList.length;
      selectAllCheckbox.indeterminate = selectedItems.size > 0 && selectedItems.size < dataList.length;
    }
  }
  
  // Update Delete Button
  function updateDeleteButton() {
    const deleteButton = document.getElementById("deleteButton");
    const deleteText = document.getElementById("deleteText");
    const deleteIcon = document.getElementById("deleteIcon");
    
    if (!deleteButton) return;
    
    if (selectedItems.size > 0) {
      deleteText.textContent = `Hapus yang Dipilih (${selectedItems.size})`;
      deleteIcon.className = "fas fa-check-square";
    } else {
      deleteText.textContent = "Hapus Semua Data";
      deleteIcon.className = "fas fa-trash-alt";
    }
  }
  
  // Handle Delete (Smart function)
  function handleDelete() {
    if (selectedItems.size > 0) {
      // Delete selected items
      alertBox(`Yakin mau hapus ${selectedItems.size} data yang dipilih?`, "confirm", (yes) => {
        if (yes) {
          // Sort indices descending to avoid index shifting issues
          const indicesToDelete = Array.from(selectedItems).sort((a, b) => b - a);
          indicesToDelete.forEach(index => {
            dataList.splice(index, 1);
          });
          selectedItems.clear();
          
          // Exit checkbox mode and return to normal view
          isCheckboxMode = false;
          const headerNoText = document.getElementById("headerNoText");
          if (headerNoText) {
            headerNoText.textContent = "No";
          }
          
          saveData();
          renderTable();
          alertBox("✅ Data terpilih berhasil dihapus!", "success");
        }
      });
    } else {
      // Delete all data
      clearAllData();
        isCheckboxMode = false;
          const headerNoText = document.getElementById("headerNoText");
          if (headerNoText) {
            headerNoText.textContent = "No";
          }
    }
  }
  
  // ===== RFID SERIAL PORT FUNCTIONS =====
  
  // Check browser support for Web Serial API
  function checkSerialSupport() {
    if (!('serial' in navigator)) {
      const warning = document.getElementById('browserWarning');
      if (warning) warning.classList.remove('hidden');
    } else {
      // Add event listeners for device changes (plug/unplug)
      navigator.serial.addEventListener('connect', (e) => {
        console.log('Device connected:', e.target);
        listPairedDevices();
        alertBox('🔌 Perangkat terhubung!', 'info');
      });
      
      navigator.serial.addEventListener('disconnect', (e) => {
        console.log('Device disconnected:', e.target);
        listPairedDevices();
        alertBox('🔌 Perangkat dicabut!', 'warning');
      });
    }
  }
  
  // Open RFID Settings Modal and load paired devices
  async function openRFIDSettings() {
    document.getElementById('rfidModal').classList.remove('hidden');
    await listPairedDevices();
  }
  
  // Close RFID Settings Modal
  function closeRFIDSettings() {
    document.getElementById('rfidModal').classList.add('hidden');
  }
  
  // List previously paired devices
  async function listPairedDevices() {
    if (!('serial' in navigator)) return;

    try {
      const ports = await navigator.serial.getPorts();
      const deviceList = document.getElementById('deviceList');
      deviceList.innerHTML = '';

      if (ports.length === 0) {
        deviceList.innerHTML = `
          <div class="text-sm text-gray-500 text-center py-4">
            Belum ada perangkat tersimpan.<br>Klik "Scan Perangkat" untuk tambah baru.
          </div>`;
        return;
      }

      // Add paired devices to list
      ports.forEach((p, index) => {
        const info = p.getInfo();
        const friendlyName = getDeviceName(info.usbVendorId, info.usbProductId);
        
        // Check if this is the currently connected port
        const isConnected = (port === p);
        
        const deviceCard = document.createElement('button');
        
        // Dynamic styling based on connection status
        let cardStyle = 'w-full glass-input p-4 rounded-2xl transition text-left group mb-2 relative overflow-hidden';
        if (isConnected) {
            cardStyle += ' bg-green-500/20 border-green-500/50 cursor-default';
        } else {
            cardStyle += ' hover:bg-cyan-500/20 border-cyan-400/30';
        }
        deviceCard.className = cardStyle;
        
        // Dynamic Content
        const statusText = isConnected 
            ? '<i class="fas fa-link text-[10px]"></i> TERHUBUNG' 
            : '<i class="fas fa-bolt text-[10px]"></i> Klik untuk hubungkan';
            
        const statusColor = isConnected ? 'text-green-300' : 'text-green-400';
        
        deviceCard.innerHTML = `
          <div class="flex items-start gap-3 relative z-10">
            <div class="w-10 h-10 rounded-full bg-cyan-500/10 flex items-center justify-center">
              <i class="fas fa-microchip text-cyan-400 text-xl"></i>
            </div>
            <div class="flex-1">
              <div class="font-semibold text-white group-hover:text-cyan-300">
                 ${friendlyName}
              </div>
              <div class="text-xs text-gray-400 mt-1">
                ${info.usbVendorId ? `VID: 0x${info.usbVendorId.toString(16)} | PID: 0x${info.usbProductId?.toString(16)}` : 'Standard Serial Port'}
              </div>
              <div class="text-xs ${statusColor} mt-2 font-bold flex items-center gap-1">
                ${statusText}
              </div>
            </div>
            ${!isConnected ? '<i class="fas fa-chevron-right text-gray-600 group-hover:text-white transition-transform group-hover:translate-x-1"></i>' : '<i class="fas fa-check-circle text-green-400 text-xl"></i>'}
          </div>
          ${!isConnected ? '<div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000"></div>' : ''}
        `;
        
        // Only allow click if NOT connected
        if (!isConnected) {
            deviceCard.onclick = () => connectToDevice(p);
        }
        
        deviceList.appendChild(deviceCard);
      });
    } catch (err) {
      console.error('Error listing paired devices:', err);
    }
  }

  // Helper to get friendly name from VID/PID
  function getDeviceName(vid, pid) {
    if (!vid) return "Unknown Serial Device";
    
    // Map common vendors
    const vendors = {
        0x2341: "Arduino Device",
        0x1a86: "CH340 Serial (Arduino Clone)",
        0x0403: "FTDI Serial",
        0x10c4: "CP210x Serial",
        0x0525: "PL2303 Serial"
    };

    if (vendors[vid]) {
        return vendors[vid];
    }
    
    return `USB Device (0x${vid.toString(16)})`;
  }
  
  // Scan for RFID devices
  async function scanRFIDDevices() {
    if (!('serial' in navigator)) {
      alertBox('❌ Browser tidak mendukung Web Serial API!', 'error');
      return;
    }

    try {
      // Filters for common Serial/RFID chips (CH340, Arduino, FTDI, CP210x)
      const filters = [
        { usbVendorId: 0x1a86 }, // CH340 (Common in clones)
        { usbVendorId: 0x2341 }, // Arduino SA
        { usbVendorId: 0x0403 }, // FTDI
        { usbVendorId: 0x10c4 }, // Silicon Labs (CP210x)
        { usbVendorId: 0x0525 }  // Prolific (PL2303) is sometimes tricky, but safe to add
      ];

      // Request port with filters OR no filters (allow user to choose)
      // Note: Passing filters sometimes helps Chrome "see" generic devices
      // But we also want to allow "All" so we usually pass NO filters to see everything.
      // However, if user is having trouble, we can try passing filters.
      // Strategy: Request ANY port (empty list or undefined usually works best)
      // BUT, since user reported issues, let's try WITHOUT filters first (standard),
      // and if they fail, we suggest checking the driver/port.
      
      // WAIT! The screenshot shows "No compatible devices".
      // This often happens if the port is BUSY (opened by Arduino IDE).
      // Let's stick to standard no-filter request but add a Help Alert if empty.
      
      const selectedPort = await navigator.serial.requestPort();
      
      // Get port info
      const info = selectedPort.getInfo();
      
      // Display device in list
      const deviceList = document.getElementById('deviceList');
      deviceList.innerHTML = '';
      
      const deviceCard = document.createElement('button');
      deviceCard.className = 'w-full glass-input hover:bg-cyan-500/20 border-cyan-400/30 p-4 rounded-2xl transition text-left group';
      deviceCard.innerHTML = `
        <div class="flex items-start gap-3">
          <i class="fas fa-usb text-cyan-400 text-2xl mt-1"></i>
          <div class="flex-1">
            <div class="font-semibold text-white group-hover:text-cyan-300">
              ${info.usbProductId ? `USB Device (PID: ${info.usbProductId})` : 'Serial Device'}
            </div>
            <div class="text-xs text-gray-400 mt-1">
              ${info.usbVendorId ? `Vendor ID: ${info.usbVendorId}` : 'Unknown Vendor'}
            </div>
          </div>
          <i class="fas fa-check-circle text-green-400 text-xl"></i>
        </div>
      `;
      
      deviceCard.onclick = () => connectToDevice(selectedPort);
      deviceList.appendChild(deviceCard);
      
      alertBox('✅ Perangkat terdeteksi! Klik untuk hubungkan.', 'success');
      
    } catch (error) {
      console.error('Error scanning devices:', error);
      if (error.name === 'NotFoundError') {
        alertBox('❌ Tidak ada perangkat yang dipilih', 'warning');
      } else {
        alertBox('❌ Error: ' + error.message, 'error');
      }
    }
  }
  
  // Connect to RFID device
  async function connectToDevice(selectedPort) {
    try {
      // Close existing connection if any
      if (port && port.readable) {
        await disconnectDevice();
      }
      
      port = selectedPort;
      
      // Open port with common RFID reader settings
      await port.open({ 
        baudRate: 9600,
        dataBits: 8,
        stopBits: 1,
        parity: 'none'
      });
      
      // Update status
      updateDeviceStatus(true, 'Terhubung');
      alertBox('✅ Berhasil terhubung ke RFID reader!', 'success');
      
      // Start reading data
      startReading();
      
      // Close modal
      closeRFIDSettings();
      
    } catch (error) {
      console.error('Error connecting to device:', error);
      alertBox('❌ Gagal terhubung: ' + error.message, 'error');
      updateDeviceStatus(false, 'Koneksi gagal');
    }
  }
  
  // Start reading from RFID device
  async function startReading() {
    if (!port || !port.readable || isReading) return;
    
    isReading = true;
    let buffer = '';
    
    try {
      reader = port.readable.getReader();
      
      while (isReading && port.readable) {
        const { value, done } = await reader.read();
        if (done) break;
        
        // Convert bytes to string
        const text = new TextDecoder().decode(value);
        buffer += text;
        
        // Process complete lines (ended with newline or carriage return)
        const lines = buffer.split(/[\r\n]+/);
        buffer = lines.pop() || ''; // Keep incomplete line in buffer
        
        for (const line of lines) {
          const cleaned = line.trim();
          
          // VALIDATION: Filter noise & debug messages
          // Only accept if:
          // 1. Length is exactly 8 (UUID) or 11 (NIM)
          // 2. Contains only alphanumeric characters (no weird symbols)
          const isValidFormat = /^[a-zA-Z0-9]+$/.test(cleaned);
          const isValidLength = cleaned.length === 8 || cleaned.length === 11;
          
          if (cleaned && isValidFormat && isValidLength) {
            console.log('✅ Valid RFID Data:', cleaned);
            processRFIDData(cleaned);
          } else if (cleaned) {
             console.warn('⚠️ Ignored Junk/Debug Data:', cleaned);
          }
        }
      }
    } catch (error) {
      console.error('Error reading from device:', error);
      if (error.name !== 'NetworkError') {
        alertBox('❌ Error membaca data: ' + error.message, 'error');
      }
    } finally {
      if (reader) {
        reader.releaseLock();
        reader = null;
      }
      isReading = false;
    }
  }
  
  // Process RFID data
  function processRFIDData(data) {
    // 1. Set Value & Focus
    input.value = data;
    input.focus();
    
    // 2. Trigger Input Event (untuk update badge detection visual)
    const inputEvent = new Event('input', { bubbles: true });
    input.dispatchEvent(inputEvent);
    
    // 3. Trigger Enter Key Event (untuk trigger logic save)
    // Menggunakan multiple properties untuk kompatibilitas
    const enterEvent = new KeyboardEvent('keydown', {
        key: 'Enter',
        code: 'Enter',
        keyCode: 13,
        which: 13,
        bubbles: true,
        cancelable: true
    });
    
    // Dispatch event setelah delay kecil dijamin UI update dulu
    setTimeout(() => {
        input.dispatchEvent(enterEvent);
        // Feedback visual di console untuk debugging
        console.log('RFID Auto-Enter triggered for:', data);
    }, 50);
  }
  
  // Disconnect from device
  async function disconnectDevice() {
    isReading = false;
    
    if (reader) {
      try {
        await reader.cancel();
        reader.releaseLock();
      } catch (e) {
        console.error('Error releasing reader:', e);
      }
      reader = null;
    }
    
    if (port) {
      try {
        await port.close();
      } catch (e) {
        console.error('Error closing port:', e);
      }
      port = null;
    }
    
    updateDeviceStatus(false, 'Tidak terhubung');
  }
  
  // Update device status UI
  function updateDeviceStatus(connected, statusText) {
    const indicator = document.getElementById('statusIndicator');
    const status = document.getElementById('deviceStatus');
    
    if (indicator && status) {
      if (connected) {
        indicator.className = 'fas fa-circle text-green-400 animate-pulse';
        status.textContent = statusText;
      } else {
        indicator.className = 'fas fa-circle text-gray-500';
        status.textContent = statusText;
      }
    }
  }
  
  // Expose RFID functions globally
  window.openRFIDSettings = openRFIDSettings;
  window.closeRFIDSettings = closeRFIDSettings;
  window.scanRFIDDevices = scanRFIDDevices;
  
  // Expose functions globally
  window.saveToExcel = saveToExcel;
  window.clearAllData = clearAllData;
  window.toggleCheckboxMode = toggleCheckboxMode;
  window.toggleSelectAll = toggleSelectAll;
  window.handleDelete = handleDelete;


//Custom Alert
function alertBox(message, type = "success", callback = null) {
    const alertBox = document.getElementById("customAlert");
    const alertText = document.getElementById("alertText");
    const confirmModal = document.getElementById("confirmModal");
    const confirmMessage = document.getElementById("confirmMessage");
    const yesBtn = document.getElementById("confirmYes");
    const noBtn = document.getElementById("confirmNo");
  
    const colorMap = {
      success: "bg-green-500",
      error: "bg-red-500",
      info: "bg-blue-500",
      warning: "bg-yellow-400 text-black"
    };
  
    if (type === "confirm") {
      // Show confirmation modal
      confirmMessage.innerText = message;
      confirmModal.classList.remove("hidden");
  
      const cleanup = () => {
        confirmModal.classList.add("hidden");
        yesBtn.onclick = null;
        noBtn.onclick = null;
      };
  
      yesBtn.onclick = () => {
        cleanup();
        if (callback) callback(true);
      };
      noBtn.onclick = () => {
        cleanup();
        if (callback) callback(false);
      };
    } else {
      // Show slide alert
      alertBox.className = `fixed top-4 left-1/2 transform -translate-x-1/2 -translate-y-full opacity-0 text-white px-6 py-3 rounded-lg shadow-lg z-50 transition-all duration-500 ease-in-out ${colorMap[type] || "bg-green-500"}`;
      alertText.innerText = message;
  
      alertBox.classList.remove("hidden");
      setTimeout(() => {
        alertBox.classList.remove("-translate-y-full", "opacity-0");
        alertBox.classList.add("translate-y-0", "opacity-100");
      }, 10);
  
      setTimeout(() => {
        alertBox.classList.remove("translate-y-0", "opacity-100");
        alertBox.classList.add("-translate-y-full", "opacity-0");
        setTimeout(() => {
          alertBox.classList.add("hidden");
        }, 500);
      }, 2000);
    }
  }
  
  
  
  // Expose functions to global scope
  window.openRFIDSettings = openRFIDSettings;
  window.closeRFIDSettings = closeRFIDSettings;
  window.scanRFIDDevices = scanRFIDDevices;
  window.listPairedDevices = listPairedDevices; // <-- Added this

  // Cleanup on unload to close port properly
  window.addEventListener('beforeunload', async () => {
      if (port) {
          await port.close();
      }
  });

});
