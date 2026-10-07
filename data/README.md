# Data and variable definitions

The analysis uses the JD.com transaction dataset described by Shen, Tang, Wu, Yuan, and Zhou, [“JD.com: Transaction-Level Data for the 2020 MSOM Data Driven Research Challenge”](https://doi.org/10.1287/msom.2020.0900). Transactions cover March 2018. The [original INFORMS announcement](https://connect.informs.org/communities/community-home/digestviewer/viewthread?GroupId=469&MessageKey=17aed2fe-eca1-4eee-9cd0-75d200a2dc8f&hlmlt=VT) describes member access.

Raw data are not distributed in this repository. Use an authorized copy of the dataset. The executed notebook and aggregate results can be read without obtaining the raw files. Source descriptions do not imply that the author participated in the research challenge or worked for JD.com.

## Local setup

Extract these five files into `data/raw/`, keeping the names unchanged:

| File | Use |
| --- | --- |
| `JD_order_data.csv` | Order lines, discounts, prices, quantities, warehouse codes |
| `JD_sku_data.csv` | Product brand and attributes |
| `JD_delivery_data.csv` | Package arrival timestamps |
| `JD_inventory_data.csv` | Daily SKU–warehouse availability listings |
| `JD_network_data.csv` | Warehouse–region reference |

If your copy is named `Archive.zip`, put it in `data/raw/` and run `python prepare_data.py` from the project root. The helper extracts only the required files. Click and user tables are not used in this study. The original archive can remain in that ignored folder.

The supplied SKU reference contains one duplicated SKU with conflicting `attribute2` values. The pipeline retains its agreed attributes and sets the conflicting attribute to missing. No supplied order line uses that SKU. The audit table records this; joins then enforce many-to-one reference matching.

## Analytical variables

| Variable | Definition |
| --- | --- |
| Primary SKU | Line contributing the most original order value; source line order breaks ties |
| 1P-only | All order lines have `type = 1`; unknown line types stop processing |
| Dominant promotion | Largest total monetary discount component; monetary ties and gift-only orders have separate labels |
| Bundle indicator | 1 for bundle-dominant, 0 for quantity-dominant orders |
| Discount depth | Total monetary discount / original order value, bounded to [0, 2]; undefined at zero original value |
| Remote fulfillment | Any observed line has `dc_ori != dc_des`; missing warehouse codes yield missing line outcomes |
| Local-stockout proxy | Any checked line's SKU is absent from its destination warehouse's previous-day inventory listing |
| Delivery hours | Order timestamp to latest recorded package arrival; negative or >720-hour durations are missing |
| Brand/attribute cell | Primary SKU's brand, attribute1, and attribute2 combination |
| Basket controls | `log(1 + original value)` and number of order lines |

Inventory absence is a proxy, not direct evidence of a physical stockout. Previous-day checks before March 1 are missing. “Any” outcomes use available line observations; an unobserved line may conceal a remote shipment or stockout. Delivery outcomes describe orders observed in JD Logistics data and valid recorded packages.

To preserve the original specification, missing quantity is set to one; missing gift flags, discounts, and prices are set to zero; negative quantities, discounts, and prices are clipped at zero. Numeric missingness and negative counts are saved **before** these conventions are applied. Missing control categories are explicit. The accounting identity between original value, final revenue, and discounts is audited rather than assumed exact.

The public tables replace hashed primary-SKU identifiers with stable labels within a run. Order/customer records are not exported. `results/input_manifest.json` records exact input sizes and SHA-256 digests for the executed analysis.
