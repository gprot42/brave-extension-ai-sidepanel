use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let handle = app.handle();

            let new_file = MenuItemBuilder::with_id("new_file", "New File")
                .accelerator("CmdOrCtrl+N")
                .build(handle)?;
            let new_tab = MenuItemBuilder::with_id("new_tab", "New Tab")
                .accelerator("CmdOrCtrl+T")
                .build(handle)?;
            let open = MenuItemBuilder::with_id("open_file", "Open...")
                .accelerator("CmdOrCtrl+O")
                .build(handle)?;
            let save = MenuItemBuilder::with_id("save", "Save")
                .accelerator("CmdOrCtrl+S")
                .build(handle)?;
            let save_as = MenuItemBuilder::with_id("save_as", "Save As...")
                .accelerator("CmdOrCtrl+Shift+S")
                .build(handle)?;
            let close_tab = MenuItemBuilder::with_id("close_tab", "Close Tab")
                .accelerator("CmdOrCtrl+W")
                .build(handle)?;
            let close_all = MenuItemBuilder::with_id("close_all", "Close All")
                .accelerator("CmdOrCtrl+Shift+W")
                .build(handle)?;

            let print = MenuItemBuilder::with_id("print", "Print...")
                .accelerator("CmdOrCtrl+P")
                .build(handle)?;

            let settings = MenuItemBuilder::with_id("settings", "Settings...")
                .accelerator("CmdOrCtrl+,")
                .build(handle)?;

            let find = MenuItemBuilder::with_id("find", "Find...")
                .accelerator("CmdOrCtrl+F")
                .build(handle)?;
            let replace = MenuItemBuilder::with_id("replace", "Replace...")
                .accelerator("CmdOrCtrl+H")
                .build(handle)?;

            let quit = MenuItemBuilder::with_id("quit", "Quit Neo Edit")
                .accelerator("CmdOrCtrl+Q")
                .build(handle)?;

            let toggle_preview = MenuItemBuilder::with_id("toggle_preview", "Toggle Preview")
                .accelerator("CmdOrCtrl+Shift+P")
                .build(handle)?;
            let toggle_outline = MenuItemBuilder::with_id("toggle_outline", "Toggle Outline")
                .accelerator("CmdOrCtrl+Shift+O")
                .build(handle)?;
            let insert_table = MenuItemBuilder::with_id("insert_table", "Insert Table...")
                .accelerator("CmdOrCtrl+Shift+T")
                .build(handle)?;
            let export_html = MenuItemBuilder::with_id("export_html", "Export to HTML...")
                .accelerator("CmdOrCtrl+Shift+E")
                .build(handle)?;
            let export_pdf = MenuItemBuilder::with_id("export_pdf", "Export to PDF...")
                .build(handle)?;

            let file_menu = SubmenuBuilder::new(handle, "File")
                .item(&new_file)
                .item(&new_tab)
                .separator()
                .item(&open)
                .separator()
                .item(&save)
                .item(&save_as)
                .separator()
                .item(&close_tab)
                .item(&close_all)
                .separator()
                .item(&print)
                .separator()
                .item(&quit)
                .build()?;

            let edit_menu = SubmenuBuilder::new(handle, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .select_all()
                .separator()
                .item(&find)
                .item(&replace)
                .separator()
                .item(&settings)
                .build()?;

            let markdown_menu = SubmenuBuilder::new(handle, "Markdown")
                .item(&toggle_preview)
                .item(&toggle_outline)
                .separator()
                .item(&insert_table)
                .separator()
                .item(&export_html)
                .item(&export_pdf)
                .build()?;

            let menu = MenuBuilder::new(handle)
                .item(&file_menu)
                .item(&edit_menu)
                .item(&markdown_menu)
                .build()?;

            app.set_menu(menu)?;

            app.on_menu_event(move |app_handle, event| {
                let id = event.id().0.as_str();
                if id == "quit" {
                    app_handle.exit(0);
                    return;
                }
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.eval(&format!("window.__menuAction && window.__menuAction('{}')", id));
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
