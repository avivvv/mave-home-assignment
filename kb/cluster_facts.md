---
id: cluster_facts
title: Cluster fact sheet
source_urls:
  - https://usrc.lanl.gov/data/failure-data.php
  - https://www.manualsbase.com/manual/412247/server/compaq/compaq_server_sc_rms/
  - https://en.wikipedia.org/wiki/AlphaServer
  - https://en.wikipedia.org/wiki/Quadrics_(company)
  - https://www.unix.com/man_page/osf1/8/niffd/
  - https://www.unix.com/man_page/osf1/4/advfs/
categories: [hardware, interconnect, network, filesystem, node_state, boot]
---

# Cluster fact sheet

What is known about the cluster that wrote the logs. Every statement is marked with where it comes from:

- **[data]** read from the logs. Each count is printed by `notebooks/05_cluster_facts.ipynb`.
- **[source]** stated by a document listed in `kb/sources.md`.
- **[guess]** a reading of a name that neither the logs nor a source confirms.

## What the system is

- [source] The logs are the "System 20 usage event info" release of Los Alamos National Laboratory, nodes 0 to 255 (LANL failure data page).
- [guess] System 20 is a Compaq AlphaServer SC. No source says so; the vocabulary of the logs matches the contents of the AlphaServer SC RMS Reference Manual.
- [source] An AlphaServer SC is built from Alpha servers, called nodes, joined by a Quadrics interconnect (Wikipedia, AlphaServer). It is managed by RMS, the Resource Management System: daemons, command line tools and an SQL database (RMS manual, introduction).
- [guess] The nodes run Tru64 UNIX. The messages use Tru64 terms that the manual pages confirm as terms: NIFF, LMF, SRM, RIS, file domains.

## Node naming

The first field of a log line names what the line is about. It is not always a compute node.

| Name in the logs | How many | What it is | From |
|---|---|---|---|
| `node-0` to `node-255` | 256 | Compute nodes | [data], and [source] for the range |
| `node-D0` to `node-D7` | 8 | Domains. A domain reports for its nodes: every filesystem message comes from a domain, not from a node | [data] |
| `Interconnect-0N00` to `-0N03`, `Interconnect-1N00` to `-1N03` | 8 | Interconnect switch modules | [data] |
| `Interconnect-0T00` to `-0T03`, `Interconnect-1T00` to `-1T03` | 8 | Interconnect switch modules | [data] |
| `gige1` to `gige8` | 8 | Devices that report a temperature level and fan failures. Ethernet switches by their name | [data] for the count, [guess] for what they are |
| `node--tc1` to `node--tc8` | 8 | Report `responding` and `not-responding` under the component `tserver`. Terminal servers, which give console access to nodes | [data] for the count, [guess] for what they are; the RMS manual's system figure shows a terminal concentrator |
| `node-ms0` | 1 | A machine outside the 256 that reports status, temperature and its network interfaces like a node. The management server by its name | [data], [guess] for the role |
| `full` | 1 | The partition, the pool of nodes that runs user jobs. It reports under the component `partition` | [data]; [source] RMS has a partitions table |
| A bare number, such as `1873` | 2,078 | An operator command. The nodes it targets are named inside the message | [data] |

## Domains

- [data] There are 8 domains of 32 nodes each. Domain `node-D<k>` holds nodes `32k` to `32k+31`: `node-D0` is nodes 0 to 31, `node-D7` is nodes 224 to 255. So the domain of `node-<n>` is `n // 32`.
- [data] Evidence: 652 operator commands name one domain and one node, and the node is in that range in all 652. Commands that target a whole domain name exactly that range, for each of the 8 domains.
- [guess] A domain is a sub-cluster whose nodes share cluster filesystems and are managed together. No source that could be read says what a domain is.
- [data] The first node of each domain (`node-0`, `node-32`, `node-64`, `node-96`, `node-128`, `node-160`, `node-192`, `node-224`) has a special role: it serves the domain's shared file domains (next section).

## Which nodes serve filesystems

A "file domain" is a storage pool; the term is AdvFS's [source: `advfs(4)`], and that `ServerFileSystem` is AdvFS is a [guess]. The message `domain X is no longer served by node Y` names the node that was serving X. All of the following is [data].

- **The server is always inside the reporting domain.** In all 7,982 "no longer served by node" logs, the node named is one of the 32 nodes of the domain that reports the message.
- **Storage file domains (`storage<N>`).** There are 256 of them. Only `node-D0` and `node-D7` report them. They are served by 64 nodes: `node-0` to `node-31` and `node-224` to `node-255`, four file domains per node. Nodes 32 to 223 serve none.
- **The name of a storage file domain gives its server.** `storage<g><s><d>` has a group `g` from 1 to 16, a server `s` from 1 to 4 and a disk `d` from 1 to 4. Groups 1 to 8 are on nodes 0 to 31: node `(g-1)*4 + (s-1)`. Groups 9 to 16 are on nodes 224 to 255: node `224 + (g-9)*4 + (s-1)`. Example: `storage612` is served by `node-20`. This holds in 668 of the 670 logs that name a server for a storage file domain.
- **A file domain can move to another node.** The two exceptions are `storage141` and `storage142`, normally on `node-3`, reported once each as served by `node-1`.
- **Per-node file domains (`root<N>_local`, `root<N>_tmp`, `root<N>_domain`).** Each domain has its own `root1` to `root32`. `root<N>` belongs to the N-th node of the domain, node `32k + N - 1`. `root<N>_local` and `root<N>_tmp` are served by that node in every log (1,742 and 1,718 logs). `root<N>_domain` is served by that node in 1,936 of 2,212 logs and by the first node of the domain in the other 276.
- **File domains shared by a whole domain** (`cluster_root_backup`, `cluster_usr_backup`, `cluster_var_backup`, `root_domain`, `usr_domain`, `var_domain`) are served by the first node of the domain in every log that names their server.
- So a problem on a storage file domain points at one of 64 nodes, which the name identifies, and a problem on a shared file domain points at the first node of the reporting domain.

## Interconnect switches

- [source] The interconnect of an AlphaServer SC is Quadrics' QsNet (Wikipedia). The RMS manual has an appendix on link states and link errors; it could not be read.
- [data] 16 switch modules report under the component `switch_module`: 8 with `N` in the name and 8 with `T`, numbered `00` to `03` under a leading `0` or `1`.
- [guess] The leading digit is one of two separate networks ("rails"), `N` modules connect to nodes and `T` modules sit above them. No source confirms any of this.
- [data] The two kinds behave differently. `Link error on broadcast tree` and the other broadcast errors come almost only from `Interconnect-0T00` and `Interconnect-1T00`. The fan speed report comes from one module only, `Interconnect-0N00`.
- [data] All 16 modules report link errors, power and control status. PSU status lines come from 7 of them.

## Networks on a node

- [source] NIFF, the Network Interface Failure Finder, watches a node's network interfaces and tests one that went quiet (`niffd(8)`).
- [data] The NIFF messages name three interfaces, each on its own network: `ee0` on network `10.128.0.0`, `alt0` on `5.5.224.0` or `5.5.226.0`, and `scip0` on `10.96.0.0`.
- [guess] `ee0` is the management ethernet, `alt0` a gigabit ethernet card, and `scip0` IP carried over the interconnect.
- [source] All nodes are connected to a management network (RMS manual, overview).
