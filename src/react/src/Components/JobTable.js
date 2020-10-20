import React from 'react';
import Link from 'found/lib/Link';
import { Table, Badge } from 'react-bootstrap';
import InfiniteScroll from 'react-infinite-scroll-component';
import getBadgeType from './getBadgeType';


const JobTable = ({data, match, router, hasMore, loadMore, myJobs}) => (
    <InfiniteScroll
        dataLength={data.edges.length}
        next={loadMore}
        hasMore={hasMore}
        loader='Scroll to load more...'
    >
        <Table>
            <thead>
                <tr>
                    {!myJobs && <th>User</th>}
                    <th>Name</th>
                    <th>Description</th>
                    <th className="text-center">Status</th>
                    <th className="text-center">Labels</th>
                    <th className="text-center">Actions</th>
                </tr>
            </thead>
            <tbody>
                {data.edges.length > 0 ? data.edges.map(({node}) => <tr key={node.id}>
                    {!myJobs && <td>{node.user}</td>}
                    <td>{node.name}</td>
                    <td>{node.description}</td>
                    <td className="text-center">
                        <Badge 
                            key={node.jobStatus.name } 
                            variant="primary"
                            pill>
                            {node.jobStatus.name}
                        </Badge>
                    </td>
                    <td className="text-center">
                        {
                            node.labels.map(({name}) => 
                                <Badge 
                                    key={name} 
                                    variant={getBadgeType(name)} 
                                    className="mr-1">
                                    {name}
                                </Badge>
                            )
                        }
                    </td>
                    <td className="text-center">
                        <Link 
                            key={node.id}
                            size="sm" 
                            variant="outline-primary" 
                            to={{pathname: '/bilby/job-results/' + node.id + '/'}} 
                            activeClassName="selected" 
                            exact 
                            match={match} 
                            router={router}>
                              View
                        </Link>
                    </td>
                </tr>)
                    : <tr><td colSpan='5'>Create a new job or try searching 'Any time'.</td></tr>}
            </tbody>
        </Table>
    </InfiniteScroll>
);

JobTable.defaultProps = {
    myJobs: false
};

export default JobTable;
