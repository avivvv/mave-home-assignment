# Sources

Public documentation that matches the vocabulary of the HPC logs. All were checked on 2026-10-07.

"Read" says how much of the source could actually be read. "Text checked" means the statements in the row were found in the page's own text. A source marked "search result only" was not opened, and nothing in the knowledge base may cite it until it is.

## The dataset

| Title | URL | What it covers | Read |
|---|---|---|---|
| Loghub, HPC dataset README | https://github.com/logpai/loghub/tree/master/HPC | Says the logs come from System 20 of the high performance computing cluster at Los Alamos National Laboratory (LANL), and that the original download link is dead. Gives no description of the columns | Text checked |
| Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics | https://arxiv.org/pdf/2008.06448 | Describes System 20 as 49 nodes with 6,152 cores. This does not fit the logs, which name 256 nodes | Search result only |
| LANL, Failure Data | https://usrc.lanl.gov/data/failure-data.php | Lists the original release: "System 20 usage event info - nodes number from zero", 433,490 records, file `LA-UR-06-0803-MX20_NODES_0_TO_255_EVENTS.tar.gz`. `data/original_dataset/HPC.log` has exactly 433,490 lines. Next to it are "System 20 usage with domain info" and "System 20 node internal disk failure info". The file names confirm nodes 0 to 255 and that the system has domains. The download links are FTP addresses and were not tried | Text checked |
| USENIX Computer Failure Data Repository | https://www.usenix.org/cfdr-data | Describes the LANL data: 22 systems, December 1996 to November 2005. Also lists "HPC2", a disk replacement log from a 256-node LANL cluster of 4-processor nodes, January 2004 to July 2006. The size and dates fit these logs; the page does not say it is the same system | Text checked for HPC2 |

## The cluster's management software

| Title | URL | What it covers | Read |
|---|---|---|---|
| Compaq AlphaServer SC RMS Reference Manual, Quadrics Supercomputers World, version 7, 2001-06-22, AA-RLAZB-TE, 194 pages | https://www.manualsbase.com/manual/412247/server/compaq/compaq_server_sc_rms/ | RMS is the Resource Management System of an AlphaServer SC: UNIX daemons, command line tools and an SQL database. Application nodes are reached through RMS. All nodes are connected to a management network, and a figure of the system shows a terminal concentrator and a switch. The table of contents lists the parts that match the logs: commands `rcontrol`, `rinfo`, `rmsquery`, `nodestatus`; chapter 8, Event Handling, with a list of events generated; chapter 10, The RMS Database, with a partitions table; appendix A, interconnect terms, link states and link errors; appendix B, RMS status values | Text checked, pages 1 to 20 only: title, contents, introduction, start of the overview. The site's PDF link returns "not found" |
| The same manual on another host | https://manualmachine.com/compaq/scrms/1029902-user-manual/ | A search result quotes it: the RMS daemon writes event descriptions to the events table when it detects anomalies such as a node crash or a high temperature reading | Search result only. The page refuses automated requests |
| Quadrics (company), Wikipedia | https://en.wikipedia.org/wiki/Quadrics_(company) | QsNet is Quadrics' interconnect for high performance computing, built on its elan3 and elite3 chips. Quadrics' software included a cluster resource manager, QuadricsRms. ASCI Q at Los Alamos was built from AlphaServer SC nodes | Text checked |
| AlphaServer, Wikipedia | https://en.wikipedia.org/wiki/AlphaServer | An AlphaServer SC is a supercomputer built from DS20L, ES40 or ES45 servers, called nodes, joined by a Quadrics elan3 interconnect | Text checked |

## The operating system

| Title | URL | What it covers | Read |
|---|---|---|---|
| niffd(8), Tru64 UNIX manual page | https://www.unix.com/man_page/osf1/8/niffd/ | NIFF is the Network Interface Failure Finder. The kernel marks an interface as inactive when its traffic stops; the `niffd` daemon then sends traffic through it to find out whether it is really dead. It works through the Event Management (EVM) system | Text checked |
| lmf(8), Tru64 UNIX manual page | https://www.unix.com/man_page/osf1/8/lmf/ | LMF is the License Management Facility. It keeps a database of the software licences registered on a system | Text checked |
| advfs(4), Tru64 UNIX manual page | https://www.unix.com/man_page/osf1/4/advfs/ | AdvFS, the Advanced File System, is the default file system of Tru64 UNIX. The page speaks of its domains and filesets | Text checked |
| Installation Guide, Digital UNIX Version 4.0B or higher, 1996 | https://www.cs.auckland.ac.nz/references/unix/digital/AQTLGBTE/DOCU_014.HTM | The console mode prompt `>>>`, from which a system is booted. RIS is Remote Installation Services: to boot over the network, a system must be registered as a client on a RIS server. `genvmunix` is the generic kernel. An earlier release of the operating system than the one on this cluster | Text checked, one chapter |
| Tru64 UNIX File System Administration Handbook, section 7.2 | https://www.globalspec.com/reference/27291/203279/7-2-recovery | A search result quotes it: an AdvFS domain panic follows a metadata write error or an internal inconsistency, usually signals a hardware problem, and stops further access to the domain | Search result only. The page refuses automated requests |

## Not found

- The body of the RMS Reference Manual: the events table and its fields, the list of events, the status values, the link errors.
- The Compaq AlphaServer SC System Administration Guide, which the RMS manual names as its companion. It is the likely home of the boot and shutdown commands, the domains, the console and the hardware monitoring.
- Any TruCluster documentation for the cluster filesystem messages. The manual pages `cfsmgr(8)` and `clu_add_member(8)` are not on the site that has the other Tru64 pages.
- LANL's machine list (`LA-UR-05-7318-1995-2005_LANL_Machine_List_and_Layouts.xlsx`), which would state what System 20 is. Its link is an FTP address.
