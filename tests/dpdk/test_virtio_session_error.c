/* SPDX-License-Identifier: MIT
 * Exercise backend rejection through the actual virtio control queue.
 * QEMU's built-in backend accepts AES-CBC but rejects cipher/auth chaining.
 */
#include <errno.h>
#include <stdio.h>

#include <rte_cryptodev.h>
#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_mempool.h>

int
main(int argc, char **argv)
{
	struct rte_cryptodev_config config = { .socket_id = 0, .nb_queue_pairs = 1 };
	struct rte_cryptodev_qp_conf queue = { .nb_descriptors = 128 };
	struct rte_crypto_sym_xform cipher = { 0 }, auth = { 0 };
	struct rte_mempool *pool = NULL;
	uint8_t cipher_key[16] = { 0 }, auth_key[20] = { 0 };
	uint8_t dev_id;
	void *session;
	int result = 1, configured = 0, started = 0;

	if (rte_eal_init(argc, argv) < 0)
		return 2;
	if (rte_cryptodev_devices_get("crypto_virtio", &dev_id, 1) != 1)
		goto done;
	if (rte_cryptodev_configure(dev_id, &config) != 0)
		goto done;
	configured = 1;
	pool = rte_cryptodev_sym_session_pool_create("virtio_error_sessions", 2,
		rte_cryptodev_sym_get_private_session_size(dev_id), 0, 0, 0);
	if (pool == NULL)
		goto done;
	queue.mp_session = pool;
	if (rte_cryptodev_queue_pair_setup(dev_id, 0, &queue, 0) != 0 ||
	    rte_cryptodev_start(dev_id) != 0)
		goto done;
	started = 1;
	cipher.type = RTE_CRYPTO_SYM_XFORM_CIPHER;
	cipher.cipher.algo = RTE_CRYPTO_CIPHER_AES_CBC;
	cipher.cipher.op = RTE_CRYPTO_CIPHER_OP_ENCRYPT;
	cipher.cipher.key.data = cipher_key;
	cipher.cipher.key.length = sizeof(cipher_key);
	cipher.cipher.iv.length = 16;
	cipher.next = &auth;
	auth.type = RTE_CRYPTO_SYM_XFORM_AUTH;
	auth.auth.algo = RTE_CRYPTO_AUTH_SHA1_HMAC;
	auth.auth.op = RTE_CRYPTO_AUTH_OP_GENERATE;
	auth.auth.key.data = auth_key;
	auth.auth.key.length = sizeof(auth_key);
	auth.auth.digest_length = 12;

	for (unsigned int attempt = 0; attempt < 2; attempt++) {
		rte_errno = 0;
		session = rte_cryptodev_sym_session_create(dev_id, &cipher, pool);
		if (session != NULL) {
			puts("FAIL: rejected backend request returned a usable session");
			rte_cryptodev_sym_session_free(dev_id, session);
			goto done;
		}
		if (rte_errno != EIO || rte_mempool_avail_count(pool) != 2) {
			printf("FAIL: expected EIO and full session pool; errno=%d\n", rte_errno);
			goto done;
		}
	}
	/* A supported request must still succeed using the same pool and queue. */
	cipher.next = NULL;
	session = rte_cryptodev_sym_session_create(dev_id, &cipher, pool);
	if (session == NULL)
		goto done;
	if (rte_cryptodev_sym_session_free(dev_id, session) != 0 ||
	    rte_mempool_avail_count(pool) != 2)
		goto done;
	puts("PASS: backend rejection returns EIO, pool recovers, cipher session succeeds");
	result = 0;
done:
	if (started)
		rte_cryptodev_stop(dev_id);
	if (configured)
		rte_cryptodev_close(dev_id);
	rte_mempool_free(pool);
	rte_eal_cleanup();
	return result;
}
