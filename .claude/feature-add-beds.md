# Feature: Add Beds

Allow users to dynamically add beds to the General Ward or ICU mid-simulation, mirroring the existing "Add Doctor" pattern.

---

## Branch

```
git checkout main
git pull origin main
git checkout -b feature/add-beds
```

---

## What Already Exists (No Changes Needed)

- `hospital.py` already has `add_general_beds(count)` and `add_icu_beds(count)` methods
- `state_serializer.py` automatically serialises ward capacity changes
- `simulationStore.ts` already syncs ward state on every tick
- `WardState` and `Bed` types already model dynamic capacities

---

## Steps

### Step 1 — Backend: Add `add_bed` method to `SimulationEngine`

**File:** `backend/simulation/engine.py`

Find the `add_doctor` method and add a sibling method right below it:

```python
def add_bed(self, ward: str, count: int = 1) -> None:
    """Add beds to a ward mid-simulation."""
    if ward == "general_ward":
        self.hospital.add_general_beds(count)
    elif ward == "icu":
        self.hospital.add_icu_beds(count)
    else:
        logger.warning("Unknown ward %r — bed not added", ward)
        return
    new_capacity = self.hospital._wards[ward].capacity
    logger.info("Added %d bed(s) to %s. Capacity now: %d", count, ward, new_capacity)
```

---

### Step 2 — Backend: Add `add_bed` command handler to WebSocket

**File:** `backend/api/websocket.py`

In `_handle_command`, find the `elif command == "add_doctor":` block and add a sibling block after it:

```python
elif command == "add_bed":
    ward = msg.get("ward", "general_ward")
    count = int(msg.get("count", 1))
    engine.add_bed(ward, count)
    await manager.send_to(ws, {
        "type": "command_ack",
        "command": "add_bed",
        "is_running": engine.is_running,
        "tick": engine.current_tick,
    })
```

---

### Step 3 — Frontend: Add `addBed` to `useWebSocket`

**File:** `frontend/src/hooks/useWebSocket.ts`

Find the `addDoctor` line and add `addBed` right below it:

```typescript
const addBed = useCallback(
  (ward: string, count: number = 1) => sendCommand({ command: 'add_bed', ward, count }),
  [sendCommand]
);
```

Then add `addBed` to the return object at the bottom of the hook.

---

### Step 4 — Frontend: Add UI to `ControlPanel`

**File:** `frontend/src/components/controls/ControlPanel.tsx`

1. Import `addBed` from `useWebSocket` (add to the destructured list).
2. Add local state for the selected ward:
   ```tsx
   const [selectedWard, setSelectedWard] = useState<'general_ward' | 'icu'>('general_ward');
   ```
3. Add a UI block below the Doctors section, matching its style:
   ```tsx
   <div>
     <div className="flex justify-between text-xs text-gray-600 mb-1">
       <span>Beds</span>
       <span className="font-mono">
         GW {wards['general_ward']?.capacity ?? '--'} / ICU {wards['icu']?.capacity ?? '--'}
       </span>
     </div>
     <div className="flex gap-2 items-center">
       <select
         value={selectedWard}
         onChange={e => setSelectedWard(e.target.value as 'general_ward' | 'icu')}
         className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
       >
         <option value="general_ward">General Ward</option>
         <option value="icu">ICU</option>
       </select>
       <button
         onClick={() => addBed(selectedWard)}
         disabled={!connected}
         className="px-3 py-1.5 rounded-lg text-sm font-bold bg-blue-100 text-blue-700 hover:bg-blue-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
         title={`Add bed to ${selectedWard}`}
       >
         +
       </button>
     </div>
   </div>
   ```
4. You'll need `wards` from `useSimulationStore` — add it to the store destructure at the top of the component:
   ```tsx
   const { connected, patients, doctors, wards } = useSimulationStore();
   ```

---

## Testing

1. Start the backend and frontend.
2. Click **Start** to run the simulation.
3. Wait for the ICU or General Ward to fill up (or trigger a surge).
4. Click **+** next to Beds — the capacity counter in the header should increment.
5. Verify in the WebSocket stream that `general_ward.capacity` or `icu.capacity` increases by 1.

---

## Commit & Push

```bash
git add backend/simulation/engine.py \
        backend/api/websocket.py \
        frontend/src/hooks/useWebSocket.ts \
        frontend/src/components/controls/ControlPanel.tsx

git commit -m "feat: add beds control — dynamically add general ward / ICU beds mid-simulation"

git push origin feature/add-beds
```

Then open a PR into `main`.
