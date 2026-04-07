# NFT Trading Bot – Project Plan

**Status**: Planning phase  
**Goal**: Build a semi-automated, safety-first NFT trading/sniping bot with strong emphasis on anonymity and human-in-the-loop control.  
**Core principle**: Never execute any real trade without explicit human approval.

## Phase 0 – Clarifications & Requirements (must be answered before coding starts)

1. **ERC-8004 Context & Confirmation**  
   ERC-8004 ("Trustless Agents" – https://eips.ethereum.org/EIPS/eip-8004) is a **Draft** EIP (Aug 2025–present) for **autonomous AI agents**, not a classic NFT asset standard.  
   - Uses ERC-721 NFTs to represent **agent identities** (unique, transferable).  
   - Adds on-chain **Reputation Registry** (feedback/ratings) and **Validation Registry** (zkML/TEE/stake-based scores).  
   - Focus: trustless discovery & interaction between agents (not direct trading/fractionalization of NFTs).  
   - Reference contracts reportedly deployed on mainnet ~Jan 2026, but spec still Draft → may change.  

   **Questions for you**:  
   - Do you want to monitor ERC-8004 events (e.g. new agent registrations, feedback, validations) for trading signals?  
     Examples: sniping NFTs listed/managed by high-reputation agents, detecting agent-driven arbitrage, rarity/pricing anomalies signaled via agents.  
   - Provide:  
     - Specific contract address(es) of the Identity/Reputation/Validation registries (canonical or custom deployments).  
     - Target agent collections/IDs or strategies involving agents.  
     - Or confirm we can **de-prioritize** ERC-8004 and focus only on standard ERC-721 + marketplace events.

2. Target blockchain(s) / networks? (e.g. Ethereum mainnet, Base, Arbitrum…)

3. Desired trading opportunities / strategies (select / describe priority):  
   - New mint sniping  
   - Floor price deviation (undervalued listings)  
   - Cross-marketplace arbitrage  
   - Rarity-based scoring + buying  
   - Volume / liquidity spikes  
   - AI-agent-related signals (if ERC-8004 relevant)  
   - Other: _______________________

## Phase 1 – Project Setup & Documentation

- Create clean project structure