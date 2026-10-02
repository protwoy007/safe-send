"""Investigator network view (NetworkX).

Builds the transaction neighbourhood of a held transfer so an analyst can see
the structure behind the score:

    current sender -> RECIPIENT -> accounts the recipient paid out to
    other senders  -> RECIPIENT
    PEERS: (a) other recipients that share >= 2 senders with this recipient, and
           (b) young accounts with the same fan-in pattern in the same period
           (both are leads for the analyst, not proof)
    DEVICES: devices shared between several sender accounts

Only information available before the transfer is used. Ground-truth labels are
never exposed. Notes are generated from fixed templates.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

DAY = 86_400
EPOCH = pd.Timestamp("1970-01-01")


def _ts(ts: pd.Timestamp) -> float:
    return (ts - EPOCH).total_seconds()


def build_network(eng, recipient_id: str, sender_id: str, ts: pd.Timestamp, amount: float,
                  device_id: str | None, days: int = 7, max_senders: int = 40, max_peers: int = 8) -> dict:
    t, t0 = _ts(ts), _ts(ts) - days * DAY
    G = nx.DiGraph()

    def age_days(acc):
        return round((t - eng.store.created[acc]) / DAY, 1)

    def add_node(acc, role):
        if acc not in G:
            G.add_node(acc, role=role, age_days=age_days(acc), account_type=eng.store.rtype.get(acc, "user"))
        elif G.nodes[acc]["role"] == "sender" and role in ("peer", "downstream"):
            G.nodes[acc]["role"] = role

    def add_edge(a, b, amt, when, kind="transfer"):
        if G.has_edge(a, b):
            G[a][b]["amount"] += amt
            G[a][b]["count"] += 1
            G[a][b]["last_ts"] = max(G[a][b]["last_ts"], when)
        else:
            G.add_edge(a, b, amount=amt, count=1, last_ts=when, kind=kind)

    add_node(recipient_id, "recipient")
    add_node(sender_id, "current_sender")

    # senders into the recipient (window, before this transfer)
    inc = [(w, s, a) for w, s, a in eng.in_edges.get(recipient_id, []) if t0 <= w < t]
    totals = {}
    for w, s, a in inc:
        totals[s] = totals.get(s, 0.0) + a
    top_senders = sorted(totals, key=totals.get, reverse=True)[:max_senders]
    keep = set(top_senders)
    for w, s, a in inc:
        if s in keep:
            add_node(s, "sender")
            add_edge(s, recipient_id, a, w)

    # where the recipient sent money after receiving it
    outs = [(w, r, a) for w, r, a in eng.out_edges.get(recipient_id, []) if t0 <= w < t]
    for w, r, a in outs:
        add_node(r, "downstream")
        add_edge(recipient_id, r, a, w)

    # peers (a) other recipients paid by the same senders (shared-sender signature)
    peer_info: dict[str, str] = {}
    shared: dict[str, set] = {}
    for s in keep | {sender_id}:
        for w, r, a in eng.out_edges.get(s, []):
            if t0 <= w < t and r != recipient_id and r != s:
                shared.setdefault(r, set()).add(s)
    for p in sorted((p for p, ss in shared.items() if len(ss & keep) >= 2), key=lambda p: -len(shared[p] & keep))[:max_peers]:
        peer_info[p] = "shares_senders"
        add_node(p, "peer")
        for s in shared[p] & keep:
            for w, r, a in eng.out_edges.get(s, []):
                if r == p and t0 <= w < t:
                    add_edge(s, p, a, w)

    # peers (b) young accounts with the same fan-in pattern in the same period (needs analyst review)
    if inc and len(peer_info) < max_peers:
        span = (min(w for w, _, _ in inc), max(w for w, _, _ in inc))
        for r, lst in eng.in_edges.items():
            if r == recipient_id or r in peer_info or not lst or lst[-1][0] < t0:
                continue
            recent = [(w, s) for w, s, _ in lst if t0 <= w < t]
            if len({s for _, s in recent}) < 3 or (t - eng.store.created[r]) / DAY > 30:
                continue
            lo, hi = min(w for w, _ in recent), max(w for w, _ in recent)
            if lo <= span[1] + 86_400 and hi >= span[0] - 86_400:      # active in overlapping period (+/- 1 day)
                peer_info[r] = "similar_pattern"
                add_node(r, "peer")
                G.add_edge(recipient_id, r, amount=0.0, count=1, last_ts=hi, kind="similar_pattern")
                if len(peer_info) >= max_peers:
                    break
    peers = list(peer_info)

    # the transfer under review
    add_edge(sender_id, recipient_id, float(amount), t, kind="pending")

    # devices shared across sender accounts
    device_nodes = []
    if device_id:
        others = sorted(eng.store.dev_senders.get(device_id, set()) - {sender_id})[:10]
        if others:
            dn = f"device:{device_id}"
            G.add_node(dn, role="device", age_days=None, account_type="device")
            for acc in [sender_id] + others:
                add_node(acc, "sender")
                G.add_edge(acc, dn, amount=0.0, count=1, last_ts=t, kind="uses_device")
            device_nodes.append(dn)

    # ---- graph metrics (NetworkX)
    und = G.to_undirected()
    comp = next((c for c in nx.connected_components(und) if recipient_id in c), {recipient_id})
    distinct_senders = len({s for s in G.predecessors(recipient_id)} - {sender_id}) + 1
    paid_out = sum(G[recipient_id][r]["amount"] for r in G.successors(recipient_id))
    paid_in = sum(G[s][recipient_id]["amount"] for s in G.predecessors(recipient_id)
                  if G[s][recipient_id]["kind"] != "pending")
    to_agents = [r for r in G.successors(recipient_id) if G.nodes[r]["account_type"] == "agent"]
    metrics = {
        "window_days": days,
        "recipient_age_days": age_days(recipient_id),
        "distinct_senders_incl_this": distinct_senders,
        "inflow_tk": round(paid_in),
        "outflow_tk": round(paid_out),
        "paid_out_ratio": round(paid_out / paid_in, 2) if paid_in else None,
        "paid_to_agents": len(to_agents),
        "peer_accounts": len(peers),
        "shared_devices": len(device_nodes),
        "component_size": len(comp),
        "pagerank_recipient": round(nx.pagerank(G, weight="amount").get(recipient_id, 0.0), 4) if G.number_of_edges() else 0.0,
    }

    notes = []
    if metrics["recipient_age_days"] <= 14:
        notes.append(f"Recipient account is {metrics['recipient_age_days']} days old.")
    if distinct_senders >= 4:
        notes.append(f"Received money from {distinct_senders} different senders in {days} days (including this transfer).")
    n_shared = sum(v == "shares_senders" for v in peer_info.values())
    n_similar = sum(v == "similar_pattern" for v in peer_info.values())
    if n_shared:
        notes.append(f"{n_shared} other recipient account(s) share at least 2 senders with it (possible coordinated ring).")
    if n_similar:
        notes.append(f"{n_similar} other young account(s) show the same fan-in pattern in the same period "
                     "(possibly related; analyst review needed).")
    if to_agents:
        notes.append(f"It paid out to {len(to_agents)} agent account(s) after receiving funds (possible cash-out).")
    if metrics["paid_out_ratio"] is not None and metrics["paid_out_ratio"] >= 0.8:
        notes.append("Most of the received money has already left the account.")
    if device_nodes:
        notes.append("This device was used by other sender accounts.")
    if not notes:
        notes.append("No unusual network structure found in this window.")

    nodes = [{"id": n, "role": d["role"], "age_days": d["age_days"], "account_type": d["account_type"],
              "in_degree": G.in_degree(n), "out_degree": G.out_degree(n)} for n, d in G.nodes(data=True)]
    edges = [{"source": a, "target": b, "amount": round(d["amount"]), "count": d["count"], "kind": d["kind"],
              "time": str(EPOCH + pd.Timedelta(seconds=d["last_ts"]))} for a, b, d in G.edges(data=True)]
    return {"recipient_id": recipient_id, "nodes": nodes, "edges": edges, "metrics": metrics, "notes": notes,
            "peers": [{"id": p, "reason": r} for p, r in peer_info.items()], "note_source": "NetworkX graph analysis + fixed templates"}
