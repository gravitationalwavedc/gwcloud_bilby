import React from 'react';
import { Table } from 'react-bootstrap';
import JobTableBody from './JobTableBody';
import InfiniteScroll from 'react-infinite-scroll-component';


const JobTable = ({data, match, router, hasMore, loadMore, myJobs}) => (<InfiniteScroll
    dataLength={data && data.edges.length || 0}
    next={loadMore}
    hasMore={hasMore}
    loader='Scroll to load more...'
>
    <JobTableBody data={data} myJobs={myJobs} match={match} router={router} />
</InfiniteScroll>);

JobTable.defaultProps = {
    myJobs: false
};

export default JobTable;
