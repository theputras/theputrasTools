-- ==========================================================
-- SEED DATA: TOOLS & PERMISSIONS
-- ==========================================================

-- Tool: Manajemen Ultah
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Manajemen Ultah', 'manajemen_ultah', 'Kelola data ulang tahun & sync ke Google Calendar')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Pembayaran QRIS
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Pembayaran QRIS', 'pembayaran_qris', 'Generate QRIS via iPaymu untuk pembayaran')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Cari Komunitas
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Cari Komunitas', 'cari_komunitas', 'Pencarian data mahasiswa/staff')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Log Program
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Log Program', 'log_program', 'Catatan update sistem (Changelog)')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Sosmed Download
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Sosmed Downloader', 'sosmed_download', 'Unduh media sosial')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Logbook Magang
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Logbook Magang', 'logbook_magang', 'Catat kegiatan harian & eksport ke Word')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- ==========================================================
-- SEED DATA: RAMADHAN
-- ==========================================================

-- Seed: Ramadhan 1447 H (2026)
INSERT INTO ramadan_config (hijri_year, start_ramadan_muhammadiyah, start_ramadan_pemerintah, total_days)
VALUES (1447, '2026-02-17', '2026-02-18', 30)
ON CONFLICT (hijri_year) DO UPDATE SET hijri_year = EXCLUDED.hijri_year;

-- ==========================================================
-- SEED DATA: ROLE KONSELOR
-- ==========================================================

-- Role: Admin (id = 1)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (1, 'Admin', 'Administrator sistem')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Dosen (id = 2) --> [TAMBAHAN BARU UNTUK MENGHINDARI FK ERROR]
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (2, 'Dosen', 'User Dosen')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Mahasiswa (id = 3)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (3, 'Mahasiswa', 'User mahasiswa (default)')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Konselor (id = 5)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (5, 'Konselor', 'Konselor mahasiswa — akses ke dashboard konseling')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Bimbasi / Bimbingan Sebaya Mahasiswa (id = 6)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (6, 'Bimbasi', 'Bimbingan Sebaya Mahasiswa — akses terbatas ke konseling')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Satgas PPKPT (id = 7)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (7, 'Satgas PPKPT', 'Satgas Pencegahan dan Penanganan Kekerasan — akses monitoring konseling')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- ==========================================================
-- SEED DATA: USER KONSELOR (fitriyah)
-- ==========================================================

-- Password: fit8872 (bcrypt hashed)
INSERT INTO users (username, email, password, role_id)
VALUES ('fitriyah', 'fitriyah@dinamika.ac.id', '$2b$12$xewcwtKsmLirZwdZOGhVt.XS2hgbeaoc1qlA1cot4ozs0CONowsOe', 5)
ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email, role_id = EXCLUDED.role_id;

-- ==========================================================
-- SEED DATA: KONSELOR USERS (Copy dari users utama ke tabel konselor)
-- ==========================================================

-- Admin (theputras) → role Admin (1) di konselor
INSERT INTO konselor_users (source_user_id, username, password, email, role_id)
SELECT id, username, password, email, 1
FROM users WHERE username = 'theputras'
ON CONFLICT (source_user_id) DO UPDATE SET
    username = EXCLUDED.username, password = EXCLUDED.password,
    email = EXCLUDED.email, role_id = EXCLUDED.role_id;

-- Fitriyah → role Konselor (5) di konselor
INSERT INTO konselor_users (source_user_id, username, password, email, role_id)
SELECT id, username, password, email, 5
FROM users WHERE username = 'fitriyah'
ON CONFLICT (source_user_id) DO UPDATE SET
    username = EXCLUDED.username, password = EXCLUDED.password,
    email = EXCLUDED.email, role_id = EXCLUDED.role_id;

-- ==========================================================
-- SEED DATA: ROLE PERMISSIONS (Siapa aja yang bisa ngontak tools)
-- ==========================================================

-- Admin (Role 1) bisa akses semua tools
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 1, id, 1 FROM tools ON CONFLICT DO NOTHING;

-- Dosen (Role 2) bisa akses Cari Komunitas, Manajemen Ultah, Sosmed Download
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 2, id, 1 FROM tools WHERE route_name IN ('cari_komunitas', 'manajemen_ultah', 'sosmed_download') ON CONFLICT DO NOTHING;

-- Mahasiswa (Role 3) bisa akses Logbook Magang, Cari Komunitas, Sosmed Download
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 3, id, 1 FROM tools WHERE route_name IN ('logbook_magang', 'cari_komunitas', 'sosmed_download') ON CONFLICT DO NOTHING;

-- ==========================================================
-- SEED DATA: KONSELOR ROLE PERMISSIONS (Hak Akses Dinamis per Halaman)
-- page_identifier: dashboard, catat_sesi, rekap_sesi, jadwal_konsul, kelola_master, kelola_akses
-- ==========================================================

-- Admin (Role 1): Full access ALL scope di semua halaman
INSERT INTO konselor_role_permissions (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope) VALUES
(1, 'dashboard',     1, 1, 1, 1, 1, 1, 'ALL'),
(1, 'catat_sesi',    1, 1, 1, 1, 1, 1, 'ALL'),
(1, 'rekap_sesi',    1, 1, 1, 1, 1, 1, 'ALL'),
(1, 'jadwal_konsul', 1, 1, 1, 1, 1, 1, 'ALL'),
(1, 'kelola_master', 1, 1, 1, 1, 1, 1, 'ALL'),
(1, 'kelola_akses',  1, 1, 1, 1, 0, 0, 'ALL'),
(1, 'kelola_mbti',    1, 1, 1, 1, 1, 1, 'ALL')
ON CONFLICT (role_id, page_identifier) DO UPDATE SET
    can_view = EXCLUDED.can_view, can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update, can_delete = EXCLUDED.can_delete,
    can_import = EXCLUDED.can_import, can_export = EXCLUDED.can_export,
    data_scope = EXCLUDED.data_scope;

-- Konselor (Role 5): Full CRUD pada data sendiri (OWN)
INSERT INTO konselor_role_permissions (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope) VALUES
(5, 'dashboard',     1, 1, 1, 1, 1, 1, 'OWN'),
(5, 'catat_sesi',    1, 1, 1, 1, 1, 1, 'OWN'),
(5, 'rekap_sesi',    1, 1, 1, 1, 1, 1, 'OWN'),
(5, 'jadwal_konsul', 1, 1, 1, 1, 0, 0, 'OWN'),
(5, 'kelola_master', 1, 1, 1, 1, 0, 0, 'OWN'),
(5, 'kelola_akses',  0, 0, 0, 0, 0, 0, 'NONE'),
(5, 'kelola_mbti',    1, 1, 1, 1, 0, 0, 'OWN')
ON CONFLICT (role_id, page_identifier) DO UPDATE SET
    can_view = EXCLUDED.can_view, can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update, can_delete = EXCLUDED.can_delete,
    can_import = EXCLUDED.can_import, can_export = EXCLUDED.can_export,
    data_scope = EXCLUDED.data_scope;

-- Bimbasi (Role 6): CRUD terbatas, hanya data sendiri
INSERT INTO konselor_role_permissions (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope) VALUES
(6, 'dashboard',     1, 1, 1, 0, 0, 0, 'OWN'),
(6, 'catat_sesi',    1, 1, 1, 0, 0, 0, 'OWN'),
(6, 'rekap_sesi',    1, 0, 0, 0, 0, 1, 'OWN'),
(6, 'jadwal_konsul', 1, 1, 1, 0, 0, 0, 'OWN'),
(6, 'kelola_master', 0, 0, 0, 0, 0, 0, 'NONE'),
(6, 'kelola_akses',  0, 0, 0, 0, 0, 0, 'NONE'),
(6, 'kelola_mbti',    0, 0, 0, 0, 0, 0, 'NONE')
ON CONFLICT (role_id, page_identifier) DO UPDATE SET
    can_view = EXCLUDED.can_view, can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update, can_delete = EXCLUDED.can_delete,
    can_import = EXCLUDED.can_import, can_export = EXCLUDED.can_export,
    data_scope = EXCLUDED.data_scope;

-- Satgas PPKPT (Role 7): Read-only semua data (ALL scope), bisa export
INSERT INTO konselor_role_permissions (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope) VALUES
(7, 'dashboard',     1, 0, 0, 0, 0, 0, 'ALL'),
(7, 'catat_sesi',    0, 0, 0, 0, 0, 0, 'NONE'),
(7, 'rekap_sesi',    1, 0, 0, 0, 0, 1, 'ALL'),
(7, 'jadwal_konsul', 1, 0, 0, 0, 0, 0, 'ALL'),
(7, 'kelola_master', 0, 0, 0, 0, 0, 0, 'NONE'),
(7, 'kelola_akses',  0, 0, 0, 0, 0, 0, 'NONE'),
(7, 'kelola_mbti',    0, 0, 0, 0, 0, 0, 'NONE')
ON CONFLICT (role_id, page_identifier) DO UPDATE SET
    can_view = EXCLUDED.can_view, can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update, can_delete = EXCLUDED.can_delete,
    can_import = EXCLUDED.can_import, can_export = EXCLUDED.can_export,
    data_scope = EXCLUDED.data_scope;

-- Mahasiswa (Role 3): Dashboard view-only (OWN scope) untuk portal mbti
INSERT INTO konselor_role_permissions (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope) VALUES
(3, 'dashboard',     1, 0, 0, 0, 0, 0, 'OWN'),
(3, 'catat_sesi',    0, 0, 0, 0, 0, 0, 'NONE'),
(3, 'rekap_sesi',    0, 0, 0, 0, 0, 0, 'NONE'),
(3, 'jadwal_konsul', 0, 0, 0, 0, 0, 0, 'NONE'),
(3, 'kelola_master', 0, 0, 0, 0, 0, 0, 'NONE'),
(3, 'kelola_akses',  0, 0, 0, 0, 0, 0, 'NONE'),
(3, 'kelola_mbti',    0, 0, 0, 0, 0, 0, 'NONE')
ON CONFLICT (role_id, page_identifier) DO UPDATE SET
    can_view = EXCLUDED.can_view, can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update, can_delete = EXCLUDED.can_delete,
    can_import = EXCLUDED.can_import, can_export = EXCLUDED.can_export,
    data_scope = EXCLUDED.data_scope;


-- ==========================================================
-- SEED DATA: MASTER KONSELOR (Kategori Masalah & Jenis Layanan)
-- ==========================================================

-- Default Kategori Masalah
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Pribadi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Sosial') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Keluarga') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Akademik') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;

-- Default Jenis Layanan
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Individu') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Kelompok') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Bimbingan Kelompok') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konsultasi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Mediasi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;

-- Default Tindak Lanjut
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Monitoring') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Terminasi Sementara') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Rujuk ke Pihak Lain') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;

-- ==========================================================
-- SEED DATA: MBTI CONFIG
-- ==========================================================
INSERT INTO mbti_configs (config_key, config_value) VALUES ('retake_interval_days', '30') ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value;

-- ==========================================================
-- SEED DATA: MBTI 16 TIPE KEPRIBADIAN
-- ==========================================================
INSERT INTO mbti_results_info (mbti_type, title, description, characteristics, development_suggestions, suitable_professions) VALUES
('ISTJ', 'Ahli Logistik', 'Introvert, Sensing, Thinking, Judging', 'Bertanggung jawab dan dapat diandalkan; Praktis dan berorientasi pada fakta; Terorganisir dan metodis; Setia dan konsisten; Tenang namun tegas', 'Cobalah lebih terbuka terhadap ide-ide baru dan cara pandang yang berbeda; Latih fleksibilitas dalam menghadapi perubahan mendadak; Luangkan waktu untuk memahami perasaan orang lain', 'Akuntan, Auditor, Manajer Proyek, Administrator, Analis Data'),
('ISFJ', 'Pelindung', 'Introvert, Sensing, Feeling, Judging', 'Hangat dan penuh perhatian; Teliti dan bertanggung jawab; Setia dan suportif; Mengutamakan harmoni; Pekerja keras di balik layar', 'Belajar untuk mengatakan tidak dan menetapkan batasan; Jangan terlalu mengorbankan kebutuhan sendiri demi orang lain; Cobalah lebih percaya diri dalam menyampaikan pendapat', 'Perawat, Guru, Staf HR, Pustakawan, Konselor'),
('INFJ', 'Advokat', 'Introvert, Intuitive, Feeling, Judging', 'Visioner dan idealis; Berempati tinggi; Kreatif dan penuh wawasan; Teguh pada nilai-nilai; Suka menolong orang lain berkembang', 'Jangan terlalu perfeksionis terhadap diri sendiri; Belajar menerima bahwa tidak semua orang bisa ditolong; Luangkan waktu untuk diri sendiri agar tidak kelelahan emosional', 'Psikolog, Konselor, Penulis, Pekerja Sosial, Dosen'),
('INTJ', 'Arsitek', 'Introvert, Intuitive, Thinking, Judging', 'Pemikir strategis dan visioner; Independen dan percaya diri; Ambisius dan terencana; Analitis dan objektif; Standar tinggi terhadap diri sendiri dan orang lain', 'Latih kesabaran terhadap orang yang berpikir lebih lambat; Cobalah lebih menghargai aspek emosional dalam hubungan; Belajar mendelegasikan tugas dan mempercayai orang lain', 'Ilmuwan, Insinyur, Arsitek, Analis Bisnis, Software Architect'),
('ISTP', 'Virtuoso', 'Introvert, Sensing, Thinking, Perceiving', 'Praktis dan logis; Cepat tanggap dalam situasi darurat; Suka memecahkan masalah teknis; Mandiri dan fleksibel; Tenang dan rasional', 'Cobalah lebih terbuka dalam mengekspresikan perasaan; Latih komitmen jangka panjang; Belajar untuk lebih sabar dalam situasi yang membutuhkan diplomasi', 'Teknisi, Software Engineer, Ahli IT, Pilot, Mekanik'),
('ISFP', 'Petualang', 'Introvert, Sensing, Feeling, Perceiving', 'Artistik dan sensitif; Fleksibel dan spontan; Menghargai kebebasan dan keindahan; Baik hati dan rendah hati; Hidup di saat ini', 'Belajar untuk lebih tegas dalam mengambil keputusan; Jangan takut untuk mengekspresikan pendapat; Cobalah membuat perencanaan jangka panjang', 'Desainer Grafis, Fotografer, Musisi, Seniman, Pekerja Kreatif'),
('INFP', 'Mediator', 'Introvert, Intuitive, Feeling, Perceiving', 'Idealis dan empatik; Kreatif dan imajinatif; Setia pada nilai-nilai personal; Pencari makna dalam hidup; Sensitif dan penuh perasaan', 'Belajar untuk lebih realistis dalam menetapkan ekspektasi; Jangan terlalu keras pada diri sendiri; Latih kemampuan untuk mengambil tindakan, bukan hanya bermimpi', 'Penulis, Desainer, Psikolog, Penerjemah, Konselor Seni'),
('INTP', 'Ahli Logika', 'Introvert, Intuitive, Thinking, Perceiving', 'Inovatif dan haus pengetahuan; Logis dan analitis; Suka eksperimen dan teori; Independen dalam berpikir; Objektif dan kritis', 'Latih kemampuan komunikasi interpersonal; Cobalah menyelesaikan proyek sebelum memulai yang baru; Belajar mempertimbangkan perasaan orang lain dalam pengambilan keputusan', 'Peneliti, Data Scientist, Software Developer, Fisikawan, Filsuf'),
('ESTP', 'Pengusaha', 'Extravert, Sensing, Thinking, Perceiving', 'Energik dan spontan; Jago mengambil keputusan cepat; Berorientasi aksi; Pragmatis dan adaptif; Senang tantangan dan risiko', 'Belajar untuk berpikir lebih jauh ke depan sebelum bertindak; Latih kesabaran dan perhatian pada detail; Cobalah lebih sensitif terhadap perasaan orang lain', 'Sales, Wirausaha, Jurnalis Lapangan, Atlet, Marketing'),
('ESFP', 'Penghibur', 'Extravert, Sensing, Feeling, Perceiving', 'Ekspresif dan antusias; Ramah dan senang berinteraksi; Spontan dan menyenangkan; Optimis dan energik; Suka menjadi pusat perhatian', 'Belajar untuk fokus pada tujuan jangka panjang; Cobalah lebih disiplin dalam mengelola waktu; Jangan menghindari konflik yang perlu diselesaikan', 'Presenter, MC, Aktor, Influencer, Event Organizer'),
('ENFP', 'Juru Kampanye', 'Extravert, Intuitive, Feeling, Perceiving', 'Antusias dan kreatif; Energik dan mudah beradaptasi; Suka mengeksplorasi kemungkinan baru; Hangat dan empatik; Inspiratif dan optimis', 'Belajar untuk menyelesaikan apa yang sudah dimulai; Latih fokus dan konsistensi; Cobalah lebih realistis dalam menilai situasi', 'Marketer, Content Creator, HRD, Konsultan, Jurnalis'),
('ENTP', 'Pendebat', 'Extravert, Intuitive, Thinking, Perceiving', 'Cerdas dan penuh rasa ingin tahu; Suka tantangan intelektual; Inovatif dan visioner; Tegas dan argumentatif; Tidak takut melawan arus', 'Belajar untuk lebih menghargai perasaan orang lain dalam debat; Latih kesabaran untuk menyelesaikan detail; Cobalah lebih konsisten dalam menjalankan rencana', 'Pengacara, Pengusaha, Jurnalis, Konsultan Strategi, Inventor'),
('ESTJ', 'Eksekutif', 'Extravert, Sensing, Thinking, Judging', 'Praktis dan tegas; Fokus pada hasil dan efisiensi; Suka keteraturan dan struktur; Pemimpin yang natural; Bertanggung jawab dan dapat diandalkan', 'Cobalah lebih fleksibel dan terbuka terhadap pendekatan baru; Latih empati dan kesabaran terhadap orang lain; Belajar mendengarkan sebelum mengambil keputusan', 'Manajer Operasional, Direktur, Kepala Divisi, Hakim, CEO'),
('ESFJ', 'Konsul', 'Extravert, Sensing, Feeling, Judging', 'Supel dan peduli; Sangat suportif dan loyal; Menjaga keharmonisan; Terorganisir dan bertanggung jawab; Senang membantu orang lain', 'Belajar untuk tidak terlalu bergantung pada pendapat orang lain; Cobalah lebih tegas dalam menyampaikan kebutuhan sendiri; Jangan terlalu mengambil hati kritik', 'Guru, Perawat, Event Organizer, Konselor, Manajer HR'),
('ENFJ', 'Protagonis', 'Extravert, Intuitive, Feeling, Judging', 'Karismatik dan inspiratif; Empati kuat dan pengertian; Mampu memotivasi orang lain; Idealis namun terorganisir; Natural leader', 'Belajar untuk tidak terlalu memaksakan visi pada orang lain; Luangkan waktu untuk diri sendiri; Jangan merasa bertanggung jawab atas kebahagiaan semua orang', 'Guru, Coach, Pembicara Publik, Diplomat, Manajer SDM'),
('ENTJ', 'Komandan', 'Extravert, Intuitive, Thinking, Judging', 'Pemimpin tegas dan berani; Determinasi tinggi; Strategis dan efisien; Percaya diri dan ambisius; Visioner dan berorientasi tujuan', 'Belajar untuk lebih sabar dan mendengarkan ide orang lain; Cobalah lebih menghargai proses, bukan hanya hasil; Latih sensitivitas emosional', 'Manajer, Eksekutif, Pengusaha, Konsultan, Direktur')
ON CONFLICT (mbti_type) DO UPDATE SET title=EXCLUDED.title, description=EXCLUDED.description, characteristics=EXCLUDED.characteristics, development_suggestions=EXCLUDED.development_suggestions, suitable_professions=EXCLUDED.suitable_professions;-- ==========================================================
-- SEED DATA: MBTI PERTANYAAN (60 soal, 15 per dimensi)
-- choice_a = huruf pertama dimensi (E/S/T/J)
-- choice_b = huruf kedua dimensi (I/N/F/P)
-- ==========================================================

-- EI: Extraversion vs Introversion (15 soal)
INSERT INTO mbti_questions (question_text, dimension, choice_a, choice_b, sort_order) VALUES
('Saya lebih suka menghabiskan waktu bersama banyak orang', 'EI', 'Sangat setuju, saya merasa berenergi saat bersama orang lain', 'Tidak setuju, saya lebih suka waktu sendiri atau dengan sedikit orang', 1),
('Saat menghadiri acara sosial, saya cenderung...', 'EI', 'Berkenalan dengan banyak orang baru', 'Berbincang mendalam dengan satu atau dua orang saja', 2),
('Setelah seharian beraktivitas, saya memulihkan energi dengan cara...', 'EI', 'Berkumpul dan mengobrol dengan teman-teman', 'Menyendiri di tempat yang tenang', 3),
('Dalam kerja kelompok, saya lebih suka...', 'EI', 'Berdiskusi langsung dan brainstorming bersama', 'Berpikir sendiri dulu baru menyampaikan ide', 4),
('Saya merasa paling nyaman ketika...', 'EI', 'Berada di lingkungan yang ramai dan dinamis', 'Berada di lingkungan yang tenang dan damai', 5),
('Saat ada masalah, saya cenderung...', 'EI', 'Langsung membicarakannya dengan orang lain', 'Memikirkannya sendiri terlebih dahulu', 6),
('Saya lebih menikmati...', 'EI', 'Kegiatan yang melibatkan banyak interaksi sosial', 'Kegiatan yang bisa dilakukan sendiri atau berdua', 7),
('Dalam berbicara, saya cenderung...', 'EI', 'Berbicara dulu, baru berpikir', 'Berpikir dulu, baru berbicara', 8),
('Di akhir pekan, saya lebih memilih...', 'EI', 'Pergi ke tempat ramai atau menghadiri acara', 'Bersantai di rumah dengan hobi pribadi', 9),
('Saya mendapat inspirasi terbaik dari...', 'EI', 'Diskusi dan bertukar pikiran dengan orang lain', 'Perenungan dan refleksi pribadi', 10),
('Saya lebih suka bekerja di...', 'EI', 'Ruangan terbuka dengan banyak orang', 'Ruangan pribadi yang tenang', 11),
('Saat bertemu orang baru, saya...', 'EI', 'Mudah memulai percakapan', 'Menunggu orang lain yang memulai percakapan', 12),
('Saya lebih baik dalam...', 'EI', 'Menyampaikan ide secara lisan', 'Menuliskan ide secara tertulis', 13),
('Lingkaran pertemanan saya cenderung...', 'EI', 'Luas dengan banyak kenalan', 'Kecil dengan beberapa sahabat dekat', 14),
('Saya merasa terganggu ketika...', 'EI', 'Harus menghabiskan terlalu banyak waktu sendirian', 'Harus menghabiskan terlalu banyak waktu bersosialisasi', 15),

-- SN: Sensing vs Intuition (15 soal)
('Saya lebih tertarik pada...', 'SN', 'Fakta dan detail yang konkret', 'Konsep dan kemungkinan baru', 16),
('Dalam memahami sesuatu, saya lebih suka...', 'SN', 'Penjelasan yang praktis dan langkah demi langkah', 'Gambaran besar dan teori di baliknya', 17),
('Saat membaca, saya lebih menikmati...', 'SN', 'Cerita realistis berdasarkan kejadian nyata', 'Cerita imajinatif yang penuh simbolisme', 18),
('Saya lebih percaya pada...', 'SN', 'Pengalaman dan bukti nyata', 'Intuisi dan firasat', 19),
('Saya lebih memperhatikan...', 'SN', 'Apa yang terjadi saat ini', 'Apa yang mungkin terjadi di masa depan', 20),
('Saat menjelaskan sesuatu, saya cenderung...', 'SN', 'Memberikan detail dan contoh spesifik', 'Menggunakan analogi dan metafora', 21),
('Saya lebih suka pekerjaan yang...', 'SN', 'Menghasilkan sesuatu yang nyata dan terukur', 'Melibatkan ide-ide kreatif dan inovatif', 22),
('Dalam belajar, saya lebih suka...', 'SN', 'Materi yang praktis dan bisa langsung diterapkan', 'Teori dan konsep yang merangsang pemikiran', 23),
('Saya cenderung mengingat...', 'SN', 'Detail dan fakta spesifik', 'Pola umum dan kesan keseluruhan', 24),
('Saat menghadapi masalah baru, saya...', 'SN', 'Menggunakan cara yang sudah terbukti berhasil', 'Mencoba pendekatan baru yang belum pernah dicoba', 25),
('Saya lebih menghargai seseorang yang...', 'SN', 'Realistis dan berpijak pada kenyataan', 'Imajinatif dan penuh dengan ide-ide baru', 26),
('Dalam percakapan, saya lebih tertarik membahas...', 'SN', 'Hal-hal yang terjadi sekarang dan nyata', 'Kemungkinan dan ide-ide masa depan', 27),
('Saya lebih suka instruksi yang...', 'SN', 'Jelas, rinci, dan langkah per langkah', 'Fleksibel dengan ruang untuk interpretasi sendiri', 28),
('Saat melihat sesuatu yang baru, saya fokus pada...', 'SN', 'Detail dan fitur spesifiknya', 'Potensi dan kemungkinan pengembangannya', 29),
('Saya merasa frustasi ketika...', 'SN', 'Harus berurusan dengan teori yang terlalu abstrak', 'Harus berurusan dengan rutinitas yang terlalu monoton', 30),

-- TF: Thinking vs Feeling (15 soal)
('Saat mengambil keputusan, saya lebih mengandalkan...', 'TF', 'Logika dan analisis objektif', 'Perasaan dan dampaknya terhadap orang lain', 31),
('Saya lebih menghargai...', 'TF', 'Kejujuran, meskipun menyakitkan', 'Keharmonisan dan perasaan orang lain', 32),
('Saat teman curhat, saya cenderung...', 'TF', 'Memberikan solusi dan saran praktis', 'Mendengarkan dan memberikan dukungan emosional', 33),
('Dalam menilai sebuah keputusan, yang lebih penting adalah...', 'TF', 'Apakah keputusan itu logis dan adil', 'Apakah keputusan itu mempertimbangkan perasaan semua orang', 34),
('Saya lebih tergerak oleh...', 'TF', 'Argumen yang rasional dan berbasis data', 'Cerita yang menyentuh hati dan bermakna', 35),
('Kritik yang membangun menurut saya...', 'TF', 'Penting dan harus disampaikan apa adanya', 'Harus disampaikan dengan hati-hati agar tidak menyakiti', 36),
('Saya lebih suka bekerja dengan orang yang...', 'TF', 'Kompeten dan berorientasi pada hasil', 'Kooperatif dan peduli pada hubungan tim', 37),
('Saat ada konflik, saya cenderung...', 'TF', 'Mencari solusi yang paling logis dan fair', 'Mencari cara agar semua pihak merasa dihargai', 38),
('Saya lebih bangga ketika orang menyebut saya...', 'TF', 'Cerdas dan kompeten', 'Baik hati dan pengertian', 39),
('Dalam debat atau diskusi, saya...', 'TF', 'Fokus pada kebenaran argumen', 'Mempertimbangkan perasaan lawan bicara', 40),
('Saya merasa tidak nyaman ketika...', 'TF', 'Keputusan diambil berdasarkan emosi semata', 'Keputusan mengabaikan dampak emosional pada orang lain', 41),
('Bagi saya, keadilan berarti...', 'TF', 'Semua orang diperlakukan dengan standar yang sama', 'Setiap orang diperlakukan sesuai kebutuhannya masing-masing', 42),
('Saat memberikan feedback, saya...', 'TF', 'Langsung pada intinya meskipun terasa tajam', 'Membungkusnya dengan kata-kata yang lembut', 43),
('Saya lebih sering membuat keputusan dengan...', 'TF', 'Kepala (pikiran rasional)', 'Hati (perasaan dan nilai personal)', 44),
('Hal yang paling mengganggu saya adalah...', 'TF', 'Ketidaklogisan dan inkonsistensi', 'Ketidakpedulian dan kurangnya empati', 45),

-- JP: Judging vs Perceiving (15 soal)
('Saya lebih suka hidup yang...', 'JP', 'Terstruktur dan terencana', 'Fleksibel dan spontan', 46),
('Saat mengerjakan tugas, saya cenderung...', 'JP', 'Menyelesaikannya jauh sebelum deadline', 'Mengerjakannya mendekati deadline', 47),
('Rencana yang berubah mendadak membuat saya...', 'JP', 'Merasa terganggu dan tidak nyaman', 'Merasa tertantang dan bersemangat', 48),
('Meja kerja saya biasanya...', 'JP', 'Rapi dan terorganisir', 'Berantakan tapi saya tahu di mana semua barang', 49),
('Saat berlibur, saya lebih suka...', 'JP', 'Merencanakan itinerary detail sebelumnya', 'Mengalir saja dan melihat peluang yang ada', 50),
('Saya merasa lebih produktif ketika...', 'JP', 'Ada jadwal dan target yang jelas', 'Ada kebebasan untuk mengatur sendiri waktu saya', 51),
('Dalam membuat keputusan, saya lebih suka...', 'JP', 'Memutuskan dengan cepat dan bergerak', 'Menunda keputusan sampai semua informasi terkumpul', 52),
('Saya lebih menghargai...', 'JP', 'Ketepatan waktu dan kedisiplinan', 'Kreativitas dan fleksibilitas', 53),
('Saat belanja, saya cenderung...', 'JP', 'Membuat daftar belanja dan mengikutinya', 'Membeli sesuai keinginan saat itu juga', 54),
('Saya merasa puas ketika...', 'JP', 'Semua tugas sudah selesai dan tercentang', 'Saya punya banyak opsi dan kemungkinan terbuka', 55),
('To-do list bagi saya adalah...', 'JP', 'Sangat penting dan saya selalu membuatnya', 'Kadang dibuat tapi sering tidak diikuti', 56),
('Saya lebih suka proyek yang...', 'JP', 'Memiliki tahapan dan milestone yang jelas', 'Memberikan kebebasan untuk bereksperimen', 57),
('Rutinitas harian bagi saya...', 'JP', 'Penting untuk menjaga produktivitas', 'Membosankan dan saya sering ingin memecahnya', 58),
('Saat akan mulai sesuatu, saya...', 'JP', 'Merencanakan terlebih dahulu dengan matang', 'Langsung mulai dan menyesuaikan di perjalanan', 59),
('Saya lebih suka situasi yang...', 'JP', 'Dapat diprediksi dan terencana', 'Penuh kejutan dan kemungkinan baru', 60)
ON CONFLICT DO NOTHING;
