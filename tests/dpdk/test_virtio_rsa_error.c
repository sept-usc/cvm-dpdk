/* SPDX-License-Identifier: MIT
 * Reject oversized/unmapped RSA buffers before submission, then reuse the queue.
 */
#include <stdio.h>
#include <string.h>

#include <rte_cryptodev.h>
#include <rte_cycles.h>
#include <rte_eal.h>
#include <rte_mempool.h>

#define DATA_SIZE 4096
#include "test_cryptodev_rsa_test_vectors.h"

static int
submit(uint8_t dev_id, struct rte_crypto_op *op)
{
	struct rte_crypto_op *done = NULL;
	uint64_t end = rte_get_timer_cycles() + 10 * rte_get_timer_hz();

	if (rte_cryptodev_enqueue_burst(dev_id, 0, &op, 1) != 1)
		return -1;
	while (rte_cryptodev_dequeue_burst(dev_id, 0, &done, 1) == 0) {
		if (rte_get_timer_cycles() > end)
			return -1;
		rte_pause();
	}
	return done == op && done->status == RTE_CRYPTO_OP_STATUS_SUCCESS ? 0 : -1;
}

int
main(int argc, char **argv)
{
	struct rte_cryptodev_config config = { .socket_id = 0, .nb_queue_pairs = 1 };
	struct rte_cryptodev_qp_conf queue = { .nb_descriptors = 128 };
	struct rte_mempool *sessions = NULL, *ops = NULL;
	struct rte_crypto_op *op = NULL;
	struct rte_crypto_asym_xform xform = rsa_xform;
	uint8_t output[1040], original[1040], dev_id;
	void *session = NULL;
	int configured = 0, started = 0, result = 1;

	if (rte_eal_init(argc, argv) < 0)
		return 2;
	if (rte_cryptodev_devices_get("crypto_virtio_user", &dev_id, 1) != 1 ||
	    rte_cryptodev_configure(dev_id, &config) != 0)
		goto done;
	configured = 1;
	sessions = rte_cryptodev_asym_session_pool_create("rsa_bounds_sessions", 2, 0, 0, 0);
	ops = rte_crypto_op_pool_create("rsa_bounds_ops", RTE_CRYPTO_OP_TYPE_ASYMMETRIC, 2, 0, 0, 0);
	if (!sessions || !ops || rte_cryptodev_queue_pair_setup(dev_id, 0, &queue, 0) != 0 ||
	    rte_cryptodev_start(dev_id) != 0)
		goto done;
	started = 1;
	if (rte_cryptodev_asym_session_create(dev_id, &xform, sessions, &session) != 0)
		goto done;
	op = rte_crypto_op_alloc(ops, RTE_CRYPTO_OP_TYPE_ASYMMETRIC);
	if (!op)
		goto done;
	rte_crypto_op_attach_asym_session(op, session);
	memset(output, 0xa5, sizeof(output));
	memcpy(original, output, sizeof(output));
	for (unsigned int attempt = 0; attempt < 256; attempt++) {
		op->asym->rsa.op_type = RTE_CRYPTO_ASYM_OP_SIGN;
		op->asym->rsa.message.data = rsaplaintext.data;
		op->asym->rsa.message.length = rsaplaintext.len;
		op->asym->rsa.sign.data = output + 8;
		op->asym->rsa.sign.length = sizeof(rsa_n);
		switch (attempt % 4) {
		case 0: op->asym->rsa.message.length = 1025; break;
		case 1: op->asym->rsa.sign.length = 1025; break;
		case 2: op->asym->rsa.message.data = NULL; break;
		case 3: op->asym->rsa.sign.data = NULL; break;
		}
		if (rte_cryptodev_enqueue_burst(dev_id, 0, &op, 1) != 0 ||
		    memcmp(output, original, sizeof(output)) != 0) {
			puts("FAIL: invalid RSA buffer was accepted or changed output");
			goto done;
		}
	}
	op->asym->rsa.message.data = rsaplaintext.data;
	op->asym->rsa.message.length = rsaplaintext.len;
	op->asym->rsa.sign.data = output + 8;
	op->asym->rsa.sign.length = sizeof(rsa_n);
	if (submit(dev_id, op) != 0)
		goto done;
	op->asym->rsa.op_type = RTE_CRYPTO_ASYM_OP_VERIFY;
	if (submit(dev_id, op) != 0 || memcmp(output, original, 8) != 0 ||
	    memcmp(output + 8 + sizeof(rsa_n), original + 8 + sizeof(rsa_n),
		   sizeof(output) - 8 - sizeof(rsa_n)) != 0)
		goto done;
	puts("PASS: 256 invalid RSA submissions rejected; queue signs and verifies with intact canaries");
	result = 0;
done:
	rte_crypto_op_free(op);
	if (session)
		rte_cryptodev_asym_session_free(dev_id, session);
	if (started)
		rte_cryptodev_stop(dev_id);
	if (configured)
		rte_cryptodev_close(dev_id);
	rte_mempool_free(ops);
	rte_mempool_free(sessions);
	rte_eal_cleanup();
	return result;
}
