# Nimbus CL FOCIL Implementation

Implementing Fork-Choice Enforced Inclusion Lists in Nimbus Consensus Layer client

## Motivation

Fork-Choice Enforced Inclusion Lists (FOCIL, [EIP-7805](https://eips.ethereum.org/EIPS/eip-7805)) is a protocol upgrade that enhances censorship resistance in Ethereum. Under this mechanism, a distributed committee of validators, known as Inclusion List Committee, prepares a list of transactions directly from their local mempools. These lists of transactions are stored into respective Inclusion Lists (ILs) by every member of the committee.

Block proposers are required to include the transactions from these ILs in the next block. If a proposer omits the transactions from the ILs, the attesters will refuse to vote for the block, preventing it from becoming canonical.

By tightly coupling transaction availability with fork-choice enforcement, FOCIL shifts the power of transaction selection back to a decentralized committee without disrupting the block production pipeline.

## Project description

The [Nimbus Consensus Client](https://github.com/status-im/nimbus-eth2) does not yet have an implementation of FOCIL. The goal of this project is to assist the Nimbus team in implementing and validating the FOCIL spec, with the fellows primarily contributing to the testing and debugging as the core implementation progresses.

## Specification

The FOCIL implementation includes several components:

### 1. SSZ Containers
FOCIL introduces two main SSZ structures:
* `InclusionList`: Contains metadata and transactions.
* `SignedInclusionList`: Wraps the inclusion list message and signature.

### 2. Validator Client Changes
* `get_inclusion_list_committee`: Helper function to retrieve the inclusion list committee members for a given slot.
* `is_inclusion_list_committee_member`: Helper function to check if a validator is part of the committee.
* **Inclusion List Duties**: New duties for validator client to monitor the mempool, compile transaction batches, sign the `InclusionList`, and broadcast it.

### 3. P2P Networking
* Gossip Topic: New subnet configuration to handle broadcasting of `SignedInclusionList` messages.
* `validate_signed_inclusion_list`: Gossip validation logic to check signatures, slot timing, committee membership, and payload sizes.
* (`InclusionListsByRoot` / `InclusionListsByRange`): RPC methods to retrieve missing inclusion lists from peers.

### 4. Engine API & Execution Layer Changes
* `engine_newPayloadV5`: Extended method carrying `inclusionListTransactions` to EL to enable proposer to propose blocks with FOCIL transactions.
* `engine_forkchoiceUpdatedV4`: Extended method to support passing inclusion list constraints to the block builder.

### 5. Fork-Choice & Attestation Changes
* `get_head` modification: Updated head selection algorithm to enforce that only blocks satisfying FOCIL constraints are eligible canonical heads.
* `is_inclusion_list_satisfied`: Attestation check run by validators before casting votes to verify the proposed block contains all necessary transactions from the inclusion list.

## Roadmap

The work is structured into the phases below. The core implementation is led by the Nimbus team, while we (the fellows) assist across phases and take primary ownership of testing and debugging. The timeline for each phase depends largely on its complexity, and the phases are not strictly sequential — where dependencies allow, several can progress in parallel.

### Phase 0: Pools Foundation
Build and wire up the inclusion list (IL) pools that store and manage incoming inclusion lists, backed by unit tests covering insertion, lookup, and eviction behaviour.

### Phase 1: Fork-choice State
Build the IL satisfaction state within fork-choice. An aggregated pool is assembled from the inclusion lists contributed by each committee member, forming the basis for later enforcement.

### Phase 2: EL/Engine
Wire the consensus layer to the execution layer through the Engine API:
- add the IL-satisfied call on the Engine API,
- implement the `get_inclusion_list` function,
- add `inclusion_list_transactions` to the payload attributes.

### Phase 3: Networking
Bring inclusion lists onto the P2P layer:
- subscribe to and score the IL gossip topic,
- validate incoming gossip and admit it to the pool per the FOCIL rules (signature, timing, committee membership, size),
- implement request/response (`InclusionListsByRoot` / `InclusionListsByRange`) for syncing missing lists from peers.

### Phase 4: Validator Duties
Implement the validator-side logic: epoch scheduling of IL duties, compiling transactions from the local mempool, and signing and publishing the `SignedInclusionList`.

### Phase 5: Enforcement (Gloas fork-choice gated)
Gate head selection so that only FOCIL-satisfying blocks are eligible as canonical heads, and enforce that proposers include the required IL transactions.

### Phase 6: Testing & API Hardening
The phase where our contribution is most concentrated. Focus on extensive testing through the consensus-spec-tests, cross-client interop on FOCIL devnets, and hardening the APIs and edge cases surfaced along the way.

**Ordering note:** Phases 2 (EL/Engine) and 3 (Networking) are independent of each other and can be worked on in either order or concurrently. Testing and debugging (Phase 6) runs continuously alongside the earlier phases rather than only at the end.

## Possible challenges

* FOCIL is still actively being discussed and might lead to changes in structures, sizes, or other specs.
* Cross-client interop testing requires coordination across multiple client teams which introduces implementation and timeline issues.

## Goal of the project

Success looks like:
* Spec-compliant FOCIL integrated into the Nimbus consensus client, passing all relevant consensus-spec-tests.
* Nimbus passing all interop tests on FOCIL devnets alongside other CL and EL clients.
* Test suite and debugging contributions that help the Nimbus team ship a spec-compliant and mainnet-ready FOCIL implementation.

## Collaborators

### Fellows 

* **Abhivansh** ([@akronim26](https://github.com/akronim26))
* **Sagar** ([@SoarinSkySagar](https://github.com/SoarinSkySagar))

We will be pursuing this work together and divide work as we see fit with blockers and work items

### Mentors

* **Agnish** ([@agnxsh](https://github.com/agnxsh)) - Core Developer, Nimbus Client Team

## Resources

* [EIP-7805: Fork-choice enforced Inclusion Lists (FOCIL)](https://eips.ethereum.org/EIPS/eip-7805)
* [Consensus Specifications](https://github.com/ethereum/consensus-specs)
* [Nimbus Consensus Client Repository](https://github.com/status-im/nimbus-eth2)
* [Nimbus-eth2 focil Development Branch](https://github.com/status-im/nimbus-eth2/tree/focil)
* [PR #7637: FOCIL Spec Draft Implementation](https://github.com/status-im/nimbus-eth2/pull/7637)
* [PR #7290: Precursor Inclusion List Implementation](https://github.com/status-im/nimbus-eth2/pull/7290)
* [PR #7253: SSZ Container Spec Support](https://github.com/status-im/nimbus-eth2/pull/7253)