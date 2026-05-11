/**
 * file:        blkdev.c
 * description: blkdev implementation
 *              
 * credit:
 *  Peter Desnoyers, November 2016
 *  Philip Gust, March 2019
 *  Phillippe Meunier, 2020-2025
 *  Ryan Tsang, 2026
 */

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>

#include "blkdev.h"


/**
 * @brief      backing image metadata
 */
struct image {
    char * path;    // path to image file
    int fd;         // open file descriptor
    int size;       // number of blocks in device
};


/**
 * @brief      gets the size of the block device
 *
 * @param      dev   The block device
 *
 * @return     the number of block in device
 */
static int blkdev_size(struct blkdev * dev)
{
    assert(dev);
    struct image * im = dev->private;
    assert(im);

    return im->size;
}

/**
 * @brief      reads blocks from the block device
 *
 * @param      dev    The block device
 * @param[in]  start  The starting block
 * @param[in]  n      The number of blocks to read
 * @param      buf    The buffer to read to
 *
 * @return     BLKDEV_SUCCESS on success
 *             BLKDEV_E_BADADDR if any blocks do not exist (don't read)
 *             BLKDEV_E_UNAVAIL if image file not opened
 *             BLKDEV_E_FAULT on failure to read or short read from file
 */
static int blkdev_read(
    struct blkdev * dev, uint32_t start, uint32_t n, void * buf)
{
    assert(dev);
    struct image * im = dev->private;
    assert(im);

    // BLKDEV_BLKSZ is block size
    // Self Reference (SR): https://man7.org/linux/man-pages/man2/read.2.html
    // SR: https://man7.org/linux/man-pages/man2/lseek.2.html

    // check if unavailable
    if (im->fd == -1) { // If file descriptor is -1, file isn't open -> BLKDEV_E_UNAVAIL
        return BLKDEV_E_UNAVAIL;
    }

    // check block range
    // If trying to read more blocks than are available to read or trying to read no blocks -> BLKDEV_E_BADADDR
    if ((start+n-1 >= im->size) || (n == 0)) { 
        return BLKDEV_E_BADADDR;
    }

    // Before reading, need to repostion the file offset of the file descriptor to the starting block
    if(lseek(im->fd, start*BLKDEV_BLKSZ, SEEK_SET) != -1) { // Check if lseek was successful; also use SEEK_SET so file offset is set to offset bytes
        // read blocks
        if (read(im->fd, buf, n*BLKDEV_BLKSZ) == n*BLKDEV_BLKSZ) { // Check if read returns correct number of bytes read (not -1 due to short read needing to be checked) -> BLKDEV_SUCCESS
            return BLKDEV_SUCCESS;
        }
    }
    
    return BLKDEV_E_FAULT;
}


/**
 * @brief      write blocks to the block device
 *
 * @param      dev    The block device
 * @param[in]  start  The starting block
 * @param[in]  n      The number of blocks to write
 * @param      buf    The buffer to write from
 *
 * @return     BLKDEV_SUCCESS on success
 *             BLKDEV_E_BADADDR if any blocks do not exist (don't write)
 *                              or if attempting to write to superblock
 *             BLKDEV_E_UNAVAIL if image file not opened
 *             BLKDEV_E_FAULT on failure to write or short write to file
 */
static int blkdev_write(
    struct blkdev * dev, uint32_t start, uint32_t n, void * buf)
{
    assert(dev);
    struct image * im = dev->private;
    assert(im);

    // BLKDEV_BLKSZ is block size
    // SR: https://man7.org/linux/man-pages/man2/write.2.html

    // check if unavailable
    if (im->fd == -1) { // If file descriptor is -1, file isn't open -> BLKDEV_E_UNAVAIL
        return BLKDEV_E_UNAVAIL;
    }
    
    // check block range (including superblock check)
    // If trying to write more blocks than are available to write to, writing to superblock, or writing to no blocks -> BLKDEV_E_BADADDR
    if ((start+n-1 >= im->size) || (start == 0) || (n == 0)) { 
        return BLKDEV_E_BADADDR;
    }

    // Before writing, need to repostion the file offset of the file descriptor to the starting block
    if(lseek(im->fd, start*BLKDEV_BLKSZ, SEEK_SET) != -1) { // Check if lseek was successful; also use SEEK_SET so file offset is set to offset bytes
        // write blocks
        if (write(im->fd, buf, n*BLKDEV_BLKSZ) == n*BLKDEV_BLKSZ) { // Check if write returns correct number of bytes written -> BLKDEV_SUCCESS
            return BLKDEV_SUCCESS;
        }
    }

    return BLKDEV_E_FAULT;
}


/**
 * @brief      flush the block device
 *             (does nothing because no internal buffers)
 *
 * @param      dev    The block device
 * @param[in]  start  The starting block
 * @param[in]  n      The number of blocks to flush
 *
 * @return     BLKDEV_SUCCESS on success
 *             BLKDEV_E_UNAVAIL if image file not opened
 */
static int blkdev_flush(struct blkdev * dev, uint32_t start, uint32_t n)
{
    assert(dev);
    struct image * im = dev->private;
    assert(im);

    // (does nothing because no internal buffers)
    // So just check if file is unavailable?
    if (im->fd == -1) { // If file descriptor is -1, file isn't open -> BLKDEV_E_UNAVAIL
        return BLKDEV_E_UNAVAIL;
    }

    return BLKDEV_SUCCESS;
}


/**
 * @brief      closes the block device (if available)
 *
 * @param      dev   The block device
 * 
 * @note       this function must perform the following:
 *               - close the image file if opened,
 *                 setting the fd to -1 if it did so
 *               - free any allocated fields within the blkdev struct,
 *                 setting them to NULL if freed
 * 
 * @note       this function should NOT unlink the vtable
 *             this function should NOT free dev (caller's responsibility)
 */
static void blkdev_close(struct blkdev * dev)
{
    assert(dev);
    struct image * im = dev->private;
    assert(im);

    // SR: https://man7.org/linux/man-pages/man2/close.2.html
    // SR: https://pubs.opengroup.org/onlinepubs/009604499/functions/free.html

    // check if file open
    if (im->fd != -1) { // If file descriptor is not -1, file is open
        // close image file
        if (close(im->fd) != -1) { // Close the image file
            im->fd = -1; // Set fd to -1 if close() ran successfully
        }
    }

    // free allocated memory (make sure to do im->path before im for obvious reasons)
    free(im->path);
    im->path = NULL;

    free(im);

    // Since private holds the pointer to im, NULL it INSTEAD of im
    dev->private = NULL;
}

/**
 * blkdev vtable mapping
 */
static struct blkdev_ops ops = {
    .size  = blkdev_size,
    .read  = blkdev_read,
    .write = blkdev_write,
    .flush = blkdev_flush,
    .close = blkdev_close,
};


/// see header for docs
int blkdev_init(struct blkdev * dev, char * imgpath)
{
    fprintf(stdout, "blkdev_init: %s\n", imgpath);
    assert(dev);
    assert(imgpath);

    // allocate and initialize image
    struct image * im = malloc(sizeof(*im));
    if (!im) {
        return BLKDEV_E_BADDEV;
    }

    im->path = strdup(imgpath);

    if ((im->fd = open(imgpath, O_RDWR)) < 0) {
        fprintf(stderr, "can't open image %s: %s\n", imgpath, strerror(errno));
        return BLKDEV_E_BADDEV;
    }

    // access image
    struct stat sb;
    if (fstat(im->fd, &sb) < 0) {
        fprintf(stderr, "can't access image %s: %s\n", imgpath, strerror(errno));
        return BLKDEV_E_BADDEV;
    }
    // todo: should add a check that this is a regular file

    // check that file is a multiple of block size
    if (sb.st_size % BLKDEV_BLKSZ) {
        fprintf(stderr, "image size is not a multiple of block size %d: %s\n",
            BLKDEV_BLKSZ, imgpath);
        return BLKDEV_E_BADDEV;
    }

    im->size = sb.st_size / BLKDEV_BLKSZ;

    fprintf(stderr, "blkdev_init: image { fd=%d, size=%d }\n",
        im->fd, im->size);

    dev->private = (void *)im;
    dev->ops = &ops;

    return BLKDEV_SUCCESS;
}