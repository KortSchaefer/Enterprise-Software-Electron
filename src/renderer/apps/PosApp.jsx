import { useEffect, useMemo, useState } from "react";

const STATUS_OPTIONS = ["open", "firing", "ready", "closed"];

function formatCurrency(cents) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((Number(cents) || 0) / 100);
}

function formatTime(isoString) {
  if (!isoString) return "--:--";
  return new Date(isoString).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function statusClass(status) {
  return `pos-status-dot pos-status-${status || "open"}`;
}

function groupTicketItemsBySeat(items) {
  const groups = new Map();
  for (const item of items || []) {
    const seat = item.seat_label || "Seat 1";
    if (!groups.has(seat)) {
      groups.set(seat, []);
    }
    groups.get(seat).push(item);
  }
  return [...groups.entries()];
}

export default function PosApp({ businessName }) {
  const [board, setBoard] = useState([]);
  const [menu, setMenu] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [viewMode, setViewMode] = useState("selector");
  const [selectedTableId, setSelectedTableId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [filters, setFilters] = useState(["open", "firing", "ready"]);
  const [newTableNumber, setNewTableNumber] = useState("");
  const [newGuestCount, setNewGuestCount] = useState(2);
  const [activeCategoryId, setActiveCategoryId] = useState(null);

  const selectedTable = detail?.table || null;
  const ticketItems = detail?.ticket_items || [];
  const activeCategory = useMemo(() => {
    if (!menu.length) return null;
    return menu.find((category) => category.id === activeCategoryId) || menu[0];
  }, [activeCategoryId, menu]);

  async function loadTableDetail(tableId) {
    const result = await window.electronAPI.pos.getTableDetail({ tableId });
    if (!result.ok) {
      setMessage(result.error || "Failed to load table detail.");
      return false;
    }
    setDetail(result.data);
    return true;
  }

  async function loadBoard({ preserveSelection = true } = {}) {
    setLoading(true);
    const [boardResult, menuResult] = await Promise.all([
      window.electronAPI.pos.getBoard(),
      window.electronAPI.pos.getMenu(),
    ]);
    if (!boardResult.ok) {
      setMessage(boardResult.error || "Failed to load POS board.");
      setLoading(false);
      return;
    }
    if (!menuResult.ok) {
      setMessage(menuResult.error || "Failed to load POS menu.");
      setLoading(false);
      return;
    }

    const nextBoard = Array.isArray(boardResult.data) ? boardResult.data : [];
    const nextMenu = Array.isArray(menuResult.data) ? menuResult.data : [];
    setBoard(nextBoard);
    setMenu(nextMenu);
    if (!activeCategoryId && nextMenu.length) {
      setActiveCategoryId(nextMenu[0].id);
    }
    setLoading(false);

    if (!preserveSelection) {
      return;
    }

    if (selectedTableId && !nextBoard.some((table) => table.id === selectedTableId)) {
      setSelectedTableId(null);
      setDetail(null);
      setViewMode("selector");
      setMessage("The selected table is no longer active.");
      return;
    }

    if (viewMode === "order" && selectedTableId) {
      await loadTableDetail(selectedTableId);
    }
  }

  useEffect(() => {
    loadBoard({ preserveSelection: false });
    const intervalId = window.setInterval(() => {
      loadBoard();
    }, 8000);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleBoard = useMemo(() => {
    if (!filters.length) return board;
    return board.filter((table) => filters.includes(table.status));
  }, [board, filters]);

  async function openOrderEntry(tableId) {
    const loaded = await loadTableDetail(tableId);
    if (!loaded) return;
    setSelectedTableId(tableId);
    setViewMode("order");
  }

  async function handleCreateTable(event) {
    event.preventDefault();
    if (!newTableNumber.trim()) {
      setMessage("Enter a table number before opening a new table.");
      return;
    }
    const result = await window.electronAPI.pos.createTable({
      tableNumber: newTableNumber,
      guestCount: newGuestCount,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not create table.");
      return;
    }
    const nextTableId = result.data?.table?.id || null;
    setMessage(`Opened table ${newTableNumber}.`);
    setNewTableNumber("");
    await loadBoard({ preserveSelection: false });
    if (nextTableId) {
      await openOrderEntry(nextTableId);
    }
  }

  async function handleAddItem(menuItemId) {
    if (!selectedTable) return;
    const result = await window.electronAPI.pos.addItem({
      tableId: selectedTable.id,
      menuItemId,
      quantity: 1,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not add item.");
      return;
    }
    setDetail(result.data);
    await loadBoard();
  }

  async function handleUpdateQuantity(ticketItemId, quantity) {
    if (!selectedTable || quantity < 1) return;
    const result = await window.electronAPI.pos.updateItem({
      tableId: selectedTable.id,
      ticketItemId,
      quantity,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not update quantity.");
      return;
    }
    setDetail(result.data);
    await loadBoard();
  }

  async function handleRemoveItem(ticketItemId) {
    if (!selectedTable) return;
    const result = await window.electronAPI.pos.removeItem({
      tableId: selectedTable.id,
      ticketItemId,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not remove item.");
      return;
    }
    setDetail(result.data);
    await loadBoard();
  }

  async function handleStatusChange(status) {
    if (!selectedTable) return;
    const result = await window.electronAPI.pos.updateStatus({
      tableId: selectedTable.id,
      status,
      guestCount: selectedTable.guest_count,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not change status.");
      return;
    }
    setDetail(result.data);
    await loadBoard();
  }

  async function handleGuestCountChange(event) {
    if (!selectedTable) return;
    const guestCount = Number(event.target.value) || 0;
    const result = await window.electronAPI.pos.updateStatus({
      tableId: selectedTable.id,
      status: selectedTable.status,
      guestCount,
    });
    if (!result.ok) {
      setMessage(result.error || "Could not update guest count.");
      return;
    }
    setDetail(result.data);
    await loadBoard();
  }

  async function handlePrint(tableId = selectedTable?.id) {
    if (!tableId) return;
    const result = await window.electronAPI.pos.printTicket({ tableId, printType: "guest_check" });
    if (!result.ok) {
      setMessage(result.error || "Could not print ticket.");
      return;
    }
    setMessage(`Printed table ${result.data.table_number}.`);
    await loadBoard();
    if (viewMode === "order" && selectedTableId === tableId) {
      await loadTableDetail(tableId);
    }
  }

  async function handleCloseTable() {
    if (!selectedTable) return;
    const result = await window.electronAPI.pos.closeTable({ tableId: selectedTable.id });
    if (!result.ok) {
      setMessage(result.error || "Could not close table.");
      return;
    }
    setMessage(`Closed table ${result.data.table.table_number}.`);
    setSelectedTableId(null);
    setDetail(null);
    setViewMode("selector");
    await loadBoard({ preserveSelection: false });
  }

  function toggleFilter(status) {
    setFilters((current) => (current.includes(status) ? current.filter((value) => value !== status) : [...current, status]));
  }

  return (
    <main className="pos-shell">
      {viewMode === "selector" ? (
        <>
          <header className="pos-topbar">
            <form className="pos-new-table" onSubmit={handleCreateTable}>
              <input
                value={newTableNumber}
                onChange={(event) => setNewTableNumber(event.target.value)}
                placeholder="Table #"
                aria-label="Table number"
              />
              <input
                type="number"
                min="1"
                max="50"
                value={newGuestCount}
                onChange={(event) => setNewGuestCount(Number(event.target.value) || 1)}
                aria-label="Guest count"
              />
              <button type="submit">New Table</button>
            </form>
            <div className="pos-topbar-title">
              <p>Table Service POS</p>
              <h1>{businessName || "Dining Room Board"}</h1>
            </div>
            <button type="button" className="secondary-btn pos-close-button" onClick={() => window.electronAPI.window.closeSelf()}>
              Back to Menu
            </button>
          </header>

          <section className="pos-selector-shell">
            <div className="pos-selector-copy">
              <p className="pos-kicker">Table Selector</p>
              <h2>Choose a table to begin order entry</h2>
              <p className="subtitle">Open tickets stay here. Selecting any table takes the cashier to a dedicated full-screen order entry view.</p>
            </div>

            <div className="pos-board pos-board-selector">
              {loading ? <p className="subtitle">Loading POS board...</p> : null}
              {!loading && visibleBoard.length === 0 ? <p className="subtitle">No open tables match the current filters.</p> : null}
              {visibleBoard.map((table) => (
                <div key={table.id} className="pos-table-row">
                  <button type="button" className="pos-table-select pos-table-select-full" onClick={() => openOrderEntry(table.id)}>
                    <div className="pos-table-number-card">
                      <strong>{table.table_number}</strong>
                      <div className="pos-table-number-meta">
                        <span>{formatCurrency(table.subtotal_cents)}</span>
                        <span>{table.guest_count}</span>
                      </div>
                    </div>
                    <div className="pos-table-summary-card">
                      <div className="pos-table-summary-top">
                        <div className="pos-summary-lines">
                          {table.summary_lines.length ? table.summary_lines.map((line) => <p key={line}>{line}</p>) : <p className="subtitle">No items yet.</p>}
                        </div>
                        <div className="pos-status-stack">
                          <div className="pos-status-dots">
                            <span className={statusClass(table.status)} />
                            <span className={statusClass(table.ticket_status)} />
                            <span className={table.last_printed_at ? "pos-status-dot pos-status-ready" : "pos-status-dot pos-status-muted"} />
                          </div>
                          <span>{formatTime(table.opened_at)}</span>
                          <span>{formatTime(table.ticket_updated_at)}</span>
                        </div>
                      </div>
                    </div>
                  </button>
                  <button type="button" className="pos-print-detail-button" onClick={() => handlePrint(table.id)}>
                    Print
                  </button>
                </div>
              ))}
            </div>
          </section>

          <footer className="pos-filter-bar">
            {STATUS_OPTIONS.filter((status) => status !== "closed").map((status) => (
              <button
                key={status}
                type="button"
                className={filters.includes(status) ? "pos-filter-chip pos-filter-chip-active" : "pos-filter-chip"}
                onClick={() => toggleFilter(status)}
              >
                {status}
              </button>
            ))}
          </footer>
        </>
      ) : (
        <>
          <header className="pos-entry-toolbar">
            <button type="button" onClick={() => setViewMode("selector")}>Table Menu</button>
            <button type="button" onClick={() => setMessage("Clear is not available yet.")}>Clear</button>
            <button type="button" onClick={() => setMessage("Split check is not available yet.")}>Split Check</button>
            <button type="button" onClick={() => setMessage("Split seat is not available yet.")}>Split Seat</button>
            <button type="button" className="pos-exit-button" onClick={() => setViewMode("selector")}>Exit</button>
            <button type="button" onClick={() => handleStatusChange("firing")}>Order</button>
            <button type="button" onClick={() => setMessage("To Go flag is not available yet.")}>To Go</button>
            <button type="button" onClick={() => setMessage("Large party flag is not available yet.")}>Large Party</button>
            <button type="button" onClick={() => setMessage("One-time guest flag is not available yet.")}>1 Time Guest</button>
          </header>

          <section className="pos-entry-screen">
            <aside className="pos-ticket-rail">
              <div className="pos-ticket-titlebar">
                <span>Table {selectedTable?.table_number || "--"}</span>
                <span>Seat 1</span>
              </div>

              <div className="pos-seat-list">
                {groupTicketItemsBySeat(ticketItems).length ? (
                  groupTicketItemsBySeat(ticketItems).map(([seat, items]) => (
                    <div key={seat} className="pos-seat-section">
                      <h3>{seat}:</h3>
                      {items.map((item) => (
                        <button key={item.id} type="button" className="pos-seat-item" onClick={() => handleUpdateQuantity(item.id, item.quantity + 1)}>
                          <span>{item.quantity > 1 ? `${item.quantity} ` : ""}{item.item_name_snapshot}</span>
                          <strong>{formatCurrency(item.line_total_cents)}</strong>
                        </button>
                      ))}
                    </div>
                  ))
                ) : (
                  <p className="subtitle">No items on this ticket yet.</p>
                )}
              </div>

              <div className="pos-seat-tabs">
                <button type="button">Table</button>
                <button type="button">Seat 1</button>
                <button type="button">Seat 2</button>
                <button type="button">Seat 3</button>
              </div>
              <div className="pos-seat-nav">
                <button type="button">&lt;&lt;&lt;</button>
                <button type="button">&gt;&gt;&gt;</button>
              </div>
            </aside>

            <nav className="pos-category-rail">
              {menu.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  className={activeCategory?.id === category.id ? "pos-category-button pos-category-button-active" : "pos-category-button"}
                  onClick={() => setActiveCategoryId(category.id)}
                >
                  {category.name}
                </button>
              ))}
            </nav>

            <section className="pos-item-grid-panel">
              <div className="pos-item-grid">
                {(activeCategory?.items || []).map((item) => (
                  <button key={item.id} type="button" className="pos-entry-item-button" onClick={() => handleAddItem(item.id)}>
                    <strong>{item.name}</strong>
                    <span>{formatCurrency(item.price_cents)}</span>
                  </button>
                ))}
              </div>
            </section>
          </section>

          <footer className="pos-entry-footer">
            <button type="button" onClick={() => setViewMode("selector")}>Close</button>
            <div className="pos-entry-footer-actions">
              <button type="button" onClick={() => setMessage("Recipe is not available yet.")}>Recipe</button>
              <button type="button" onClick={() => selectedTable && ticketItems[0] && handleUpdateQuantity(ticketItems[0].id, ticketItems[0].quantity + 1)}>Quantity</button>
              <button type="button" onClick={() => selectedTable && ticketItems[0] && handleAddItem(ticketItems[0].menu_item_id)}>Repeat</button>
              <button type="button" onClick={() => setMessage("Modifiers are not available yet.")}>Modify</button>
              <button type="button" onClick={() => selectedTable && ticketItems[0] && handleRemoveItem(ticketItems[0].id)}>Delete</button>
            </div>
          </footer>

          <section className="pos-order-utility-panel">
            <div className="pos-order-summary-pill">
              <span>{selectedTable ? formatCurrency(selectedTable.subtotal_cents) : "$0.00"}</span>
              <span>{selectedTable?.item_count || 0} items</span>
            </div>
            <label>
              Guests
              <input type="number" min="0" max="50" value={selectedTable?.guest_count || 0} onChange={handleGuestCountChange} />
            </label>
            <label>
              Status
              <select value={selectedTable?.status || "open"} onChange={(event) => handleStatusChange(event.target.value)}>
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => handlePrint()}>Print Ticket</button>
            <button type="button" className="secondary-btn" onClick={handleCloseTable}>Close Table</button>
          </section>

        </>
      )}

      {message ? <p className="message pos-message">{message}</p> : null}
    </main>
  );
}
