/* SPDX-License-Identifier: MIT
 * A real vhost-vDPA memory-pin failure must reach rte_cryptodev_start().
 */
#include <errno.h>
#include <stdio.h>
#include <sys/resource.h>

#include <rte_cryptodev.h>
#include <rte_eal.h>
#include <rte_mempool.h>

int
main(int argc, char **argv)
{
	struct rte_cryptodev_config config = { .socket_id = 0, .nb_queue_pairs = 1 };
	struct rte_cryptodev_qp_conf queue = { .nb_descriptors = 128 };
	struct rte_mempool *pool = NULL;
	struct rte_crypto_sym_xform cipher = { 0 };
	uint8_t key[16] = { 0 };
	void *session;
	struct rlimit original, limited;
	uint8_t dev_id;
	int result = 1, configured = 0, started = 0, ret;

	if (rte_eal_init(argc, argv) < 0)
		return 2;
	if (rte_cryptodev_devices_get("crypto_virtio_user", &dev_id, 1) != 1)
		goto done;
	if (rte_cryptodev_configure(dev_id, &config) != 0)
		goto done;
	configured = 1;
	pool = rte_cryptodev_sym_session_pool_create("virtio_start_sessions", 2,
		rte_cryptodev_sym_get_private_session_size(dev_id), 0, 0, 0);
	if (pool == NULL)
		goto done;
	queue.mp_session = pool;
	if (rte_cryptodev_queue_pair_setup(dev_id, 0, &queue, 0) != 0 ||
	    getrlimit(RLIMIT_MEMLOCK, &original) != 0)
		goto done;
	limited = original;
	limited.rlim_cur = 0;
	if (setrlimit(RLIMIT_MEMLOCK, &limited) != 0)
		goto done;
	ret = rte_cryptodev_start(dev_id);
	started = ret == 0;
	if (setrlimit(RLIMIT_MEMLOCK, &original) != 0)
		goto done;
	if (ret != -EIO) {
		printf("FAIL: memory-pin failure returned %d instead of -EIO\n", ret);
		goto done;
	}
	/* Failed startup must not mark the device started or prevent a retry. */
	if (rte_cryptodev_start(dev_id) != 0)
		goto done;
	started = 1;
	cipher.type = RTE_CRYPTO_SYM_XFORM_CIPHER;
	cipher.cipher.algo = RTE_CRYPTO_CIPHER_AES_CBC;
	cipher.cipher.op = RTE_CRYPTO_CIPHER_OP_ENCRYPT;
	cipher.cipher.key.data = key;
	cipher.cipher.key.length = sizeof(key);
	cipher.cipher.iv.length = 16;
	session = rte_cryptodev_sym_session_create(dev_id, &cipher, pool);
	if (session == NULL || rte_cryptodev_sym_session_free(dev_id, session) != 0)
		goto done;
	puts("PASS: memory-pin failure returns EIO; retry and cipher session succeed");
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
